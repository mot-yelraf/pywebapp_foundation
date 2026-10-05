"""Verify application job queries, snapshots, and all-outcome persistence.

Checks include immediate cancellation, queued work, shutdown during finalization,
and safe failures rather than only successful jobs.
"""

import asyncio

import pytest
from pydantic import BaseModel

from pwaf_foundation.errors import DomainError
from pwaf_foundation.jobs import JobContext, JobDefinition, JobManager


class Input(BaseModel):
    """Empty inputs for lifecycle scenarios."""


@pytest.mark.parametrize('mode', ['success', 'failure', 'timeout', 'cancel', 'immediate', 'queued'])
def test_finalizer_receives_terminal_snapshot_once(mode):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        outcomes = []

        async def run(parameters, context):
            context.publish({'value': 0})
            entered.set()
            if mode == 'failure':
                raise DomainError('expected', 'Safe failure')
            if mode != 'success':
                await release.wait()
            return {'done': True}

        async def finalize(record):
            outcomes.append(record)
            record.result = {'mutated': True}

        manager = JobManager({'test': JobDefinition(
            Input, run, timeout=.02 if mode == 'timeout' else 10, finalize=finalize
        )}, history_size=5)
        job = manager.submit('test', {}, 'one', owner='alice')
        if mode == 'immediate':
            manager.cancel(job.id)
        else:
            await entered.wait()
        if mode == 'queued':
            queued = manager.submit('test', {}, 'two', owner='bob')
            manager.cancel(queued.id)
            manager.cancel(job.id)
        if mode == 'cancel':
            manager.cancel(job.id)
        if mode in {'success', 'failure', 'timeout'}:
            for _ in range(100):
                if manager.get(job.id).finished_at:
                    break
                await asyncio.sleep(.005)
        await manager.close()
        assert len(outcomes) == (2 if mode == 'queued' else 1)
        assert len({r.id for r in outcomes}) == len(outcomes)
        expected = 'succeeded' if mode == 'success' else (
            'failed' if mode in {'failure', 'timeout'} else 'cancelled'
        )
        record = manager.get(job.id)
        assert record.status == expected
        assert record.result != {'mutated': True}
        assert record.snapshot == (None if mode == 'immediate' else {'value': 0})
        assert all(r.finished_at for r in outcomes)
        assert manager.latest(owner='alice').id == job.id
        assert manager.latest(owner='nobody') is None
        assert not manager.list_records(owner='alice', offset=10, limit=1)
        for kwargs in ({'limit':0}, {'limit':6}, {'offset':-1}):
            with pytest.raises(ValueError):
                manager.list_records(owner='alice', **kwargs)
        detached = manager.latest(owner='alice')
        detached.status = 'queued'
        assert manager.get(job.id).status == expected
    asyncio.run(scenario())


@pytest.mark.parametrize('fail', [False, True, 'cancelled'])
def test_shutdown_waits_for_finalization_and_failure_is_safe(fail):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def run(parameters, context):
            return {'ok': True}

        async def finalize(record):
            entered.set()
            await release.wait()
            if fail == 'cancelled':
                raise asyncio.CancelledError()
            if fail:
                raise OSError('private path')

        manager = JobManager({'test': JobDefinition(Input, run, finalize=finalize)}, queue_size=0)
        job = manager.submit('test', {}, 'one')
        await entered.wait()
        assert manager.get(job.id).status == 'running'
        with pytest.raises(DomainError, match='saving'):
            manager.cancel(job.id)
        with pytest.raises(DomainError, match='capacity'):
            manager.submit('test', {}, 'two')
        close = asyncio.create_task(manager.close())
        await asyncio.sleep(0)
        assert not close.done()
        release.set()
        await close
        record = manager.get(job.id)
        assert record.status == ('failed' if fail else 'succeeded')
        if fail:
            assert record.result is None
            assert record.error.code == 'job_finalize_failed'
            assert 'private' not in record.model_dump_json()
    asyncio.run(scenario())


def test_snapshot_bounds_and_live_thread_publication():
    async def scenario():
        ready, release = asyncio.Event(), asyncio.Event()
        async def run(parameters, context):
            await asyncio.to_thread(context.publish, {'items': [0]})
            ready.set()
            await release.wait()
            return {}
        manager = JobManager({'test': JobDefinition(Input, run)})
        job = manager.submit('test', {}, 'one', 'alice')
        await ready.wait()
        snapshot = manager.get(job.id, 'alice').snapshot
        snapshot['items'].append(1)
        assert manager.get(job.id, 'alice').snapshot == {'items': [0]}
        with pytest.raises(DomainError):
            manager.get(job.id, 'bob')
        release.set()
        await manager.close()
    asyncio.run(scenario())
    context = JobContext('id', snapshot_limit=20)
    for value in ([], {'x': float('nan')}, {'text': 'é'*20}):
        with pytest.raises(ValueError):
            context.publish(value)
    with pytest.raises(ValueError):
        JobManager({}, snapshot_limit=0)


def test_finalizing_job_keeps_execution_slot_and_failed_save_is_finalized():
    async def scenario():
        finalizing, release = asyncio.Event(), asyncio.Event()
        calls, outcomes = [], []
        async def run(parameters, context):
            calls.append(context.job_id)
            return {}
        async def save(job_id, result):
            raise OSError('private storage failure')
        async def finalize(record):
            outcomes.append(record)
            finalizing.set()
            await release.wait()
        manager = JobManager({'test': JobDefinition(Input, run, save=save, finalize=finalize)})
        first = manager.submit('test', {}, 'first')
        await finalizing.wait()
        second = manager.submit('test', {}, 'second')
        await asyncio.sleep(0)
        assert calls == [first.id]
        assert outcomes[0].error.code == 'job_failed'
        assert manager.get(second.id).status == 'queued'
        release.set()
        await manager.close()
        assert len(outcomes) == 2
    asyncio.run(scenario())
