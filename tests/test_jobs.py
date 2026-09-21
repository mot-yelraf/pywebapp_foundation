"""Exercise job lifecycle, capacity, adapter cleanup, and safe failures.

Async scenarios run in isolated event loops and use bounded test operations.
"""

import asyncio
import os
import sys
import threading
import time

import pytest
from pydantic import BaseModel, ConfigDict

from pwaf_foundation.adapters import FunctionAdapter, SubprocessAdapter
from pwaf_foundation.errors import DomainError
from pwaf_foundation.jobs import JobCancelled, JobContext, JobDefinition, JobManager


class Input(BaseModel):
    """Small strict payload for independent job manager tests."""

    model_config = ConfigDict(extra="forbid", strict=True)
    value: int = 1


async def finished(manager, job_id):
    for _ in range(500):
        record = manager.get(job_id)
        if record.status in {"succeeded", "failed", "cancelled"}:
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("Job did not finish")


def test_capacity_idempotency_cancel_and_eviction():
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def run(parameters, context):
            entered.set()
            context.progress(0.5)
            await release.wait()
            return parameters

        manager = JobManager(
            {"test": JobDefinition(Input, run)}, concurrency=1, queue_size=1, history_size=2
        )
        first = manager.submit("test", {}, "first")
        await entered.wait()
        second = manager.submit("test", {"value": 2}, "second")
        assert manager.submit("test", {"value": 1}, "first").id == first.id
        for operation, payload, key, code in (
            ("test", {"value": 3}, "first", "idempotency_conflict"),
            ("test", {}, "third", "queue_full"),
            ("unknown", {}, "x", "unknown_operation"),
            ("test", {}, "", "invalid_key"),
            ("test", {"value": "bad"}, "bad", "validation_error"),
        ):
            with pytest.raises(DomainError) as exc:
                manager.submit(operation, payload, key)
            assert exc.value.code == code
        assert manager.cancel(second.id).status == "cancelled"
        manager.cancel(first.id)
        manager.cancel(first.id)  # Repeated cancellation does not interrupt cleanup.
        await asyncio.sleep(0)
        await finished(manager, first.id)
        release.set()
        third = manager.submit("test", {}, "third")
        record = await finished(manager, third.id)
        assert record.status == "succeeded"
        assert record.result == {"value": 1}
        with pytest.raises(DomainError, match="unavailable"):
            manager.get(first.id)
        with pytest.raises(DomainError, match="completed"):
            manager.cancel(third.id)
        await manager.close()
        with pytest.raises(DomainError, match="stopping"):
            manager.submit("test", {}, "stopped")

    asyncio.run(scenario())


def test_failures_and_commit_boundary():
    async def scenario():
        async def timeout(parameters, context):
            await asyncio.sleep(10)

        async def domain(parameters, context):
            raise DomainError("tool_failed", "Safe message")

        async def broken(parameters, context):
            raise RuntimeError("secret output")

        async def cooperative(parameters, context):
            raise JobCancelled()

        for runner, status, code in (
            (timeout, "failed", "job_timeout"),
            (domain, "failed", "tool_failed"),
            (broken, "failed", "job_failed"),
            (cooperative, "cancelled", None),
        ):
            manager = JobManager({"test": JobDefinition(Input, runner, timeout=0.01)})
            record = await finished(manager, manager.submit("test", {}, "key").id)
            assert record.status == status
            assert (record.error.code if record.error else None) == code
            assert "secret output" not in record.model_dump_json()
            await manager.close()

        committing, release = asyncio.Event(), asyncio.Event()

        async def good(parameters, context):
            return parameters

        async def save(job_id, result):
            committing.set()
            await release.wait()

        manager = JobManager({"test": JobDefinition(Input, good, save=save)})
        job = manager.submit("test", {}, "save")
        await committing.wait()
        with pytest.raises(DomainError, match="saving"):
            manager.cancel(job.id)
        close = asyncio.create_task(manager.close())
        await asyncio.sleep(0)
        assert not close.done()
        release.set()
        await close
        assert manager.get(job.id).status == "succeeded"

    asyncio.run(scenario())


def test_function_adapter_cleans_up_cooperatively():
    entered, exited = threading.Event(), threading.Event()

    def service(parameters, context):
        entered.set()
        try:
            while True:
                context.checkpoint()
                context.progress(0.5)
                time.sleep(0.001)
        finally:
            exited.set()

    async def scenario():
        manager = JobManager({"test": JobDefinition(Input, FunctionAdapter(service))})
        job = manager.submit("test", {}, "thread")
        assert await asyncio.to_thread(entered.wait, 2)
        await manager.close()
        assert exited.is_set()
        assert manager.get(job.id).status == "cancelled"
        adapter = FunctionAdapter(lambda parameters, context: parameters)
        assert await adapter({"value": 4}, JobContext("test")) == {"value": 4}

    asyncio.run(scenario())


def test_subprocess_output_and_errors():
    async def scenario():
        context = JobContext("test")
        adapter = SubprocessAdapter(
            lambda p: [sys.executable, "-c", "import sys; print(sys.argv[1])", p["text"]]
        )
        assert (await adapter({"text": "$(not-a-shell); &"}, context))[
            "stdout"
        ].strip() == "$(not-a-shell); &"
        for script, limit, code in (
            ("import sys; print('private', file=sys.stderr); sys.exit(2)", 1000, "tool_failed"),
            ("print('x'*1000000)", 1000, "output_limit"),
            ("import sys; sys.stderr.write('x'*1000000)", 1000, "output_limit"),
        ):
            adapter = SubprocessAdapter(
                lambda p, command=script: [sys.executable, "-c", command], output_limit=limit
            )
            with pytest.raises(DomainError) as exc:
                await asyncio.wait_for(adapter({}, context), 5)
            assert exc.value.code == code
        with pytest.raises(ValueError):
            await SubprocessAdapter(lambda p: [])({}, context)

    asyncio.run(scenario())


def test_subprocess_timeout_and_shutdown_reap_child(tmp_path):
    async def scenario():
        marker = tmp_path / "pid"
        script = (
            f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); "
            "time.sleep(30)"
        )
        adapter = SubprocessAdapter(lambda p: [sys.executable, "-c", script])
        for should_timeout in (False, True):
            marker.unlink(missing_ok=True)
            manager = JobManager(
                {"test": JobDefinition(Input, adapter, timeout=1 if should_timeout else 20)}
            )
            job = manager.submit("test", {}, "child")
            for _ in range(200):
                if marker.exists():
                    break
                await asyncio.sleep(0.01)
            assert marker.exists()
            pid = int(marker.read_text())
            if should_timeout:
                assert (await finished(manager, job.id)).error.code == "job_timeout"
            await manager.close()
            if os.name == "posix":
                with pytest.raises(ProcessLookupError):
                    os.kill(pid, 0)

    asyncio.run(scenario())


def test_invalid_job_configuration():
    async def run(parameters, context):
        return parameters

    for value in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            JobDefinition(Input, run, timeout=value)
    for kwargs in ({"concurrency": 0}, {"queue_size": -1}, {"history_size": 1}):
        with pytest.raises(ValueError):
            JobManager({}, **kwargs)
    with pytest.raises(ValueError):
        SubprocessAdapter(lambda p: [], output_limit=0)


def test_cancelled_record_can_be_evicted_before_shutdown():
    async def scenario():
        async def run(parameters, context):
            await asyncio.sleep(10)

        manager = JobManager({"test": JobDefinition(Input, run)}, queue_size=0, history_size=1)
        first = manager.submit("test", {}, "first")
        manager.cancel(first.id)
        manager.submit("test", {}, "second")
        await manager.close()
        assert not manager._tasks

    asyncio.run(scenario())


def test_cancel_during_process_creation_reaps_child(monkeypatch, tmp_path):
    async def scenario():
        original = asyncio.create_subprocess_exec
        created, release = asyncio.Event(), asyncio.Event()
        processes = []

        async def delayed_spawn(*arguments, **kwargs):
            process = await original(*arguments, **kwargs)
            processes.append(process)
            created.set()
            await release.wait()
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
        adapter = SubprocessAdapter(lambda p: [sys.executable, "-c", "import time; time.sleep(30)"])
        task = asyncio.create_task(adapter({}, JobContext("spawn")))
        await created.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[0].returncode is not None

    asyncio.run(scenario())


def test_failed_save_never_publishes_success():
    async def scenario():
        async def run(parameters, context):
            return {"value": 1}

        async def save(job_id, result):
            raise OSError("private disk failure")

        manager = JobManager({"test": JobDefinition(Input, run, save=save)})
        record = await finished(manager, manager.submit("test", {}, "fail").id)
        assert record.status == "failed"
        assert record.result is None
        assert record.error.code == "job_failed"
        await manager.close()

    asyncio.run(scenario())
