"""Exercise the shared process runner with controlled Python child processes.

No external tools or network destinations are required for these checks.
"""

import asyncio
import os
import sys

import pytest

from pwaf_foundation.errors import DomainError
from pwaf_foundation.processes import run_process


def test_streams_before_exit_and_preserves_unicode_without_capture():
    async def scenario():
        lines = []
        seen = asyncio.Event()
        def line(stream, text):
            lines.append((stream, text))
            seen.set()
        script = "import os,time; print(os.environ['PWAF_TEST_VALUE'],flush=True); time.sleep(.2)"
        task = asyncio.create_task(run_process(
            [sys.executable, '-c', script], on_line=line,
            # The fixture must emit the runner's documented UTF-8 wire format on Windows too.
            env={'PWAF_TEST_VALUE': 'é', 'PYTHONIOENCODING': 'utf-8'},
            capture=False, tail_chunks=1,
        ))
        await asyncio.wait_for(seen.wait(), 5)
        assert not task.done()
        result = await task
        assert lines == [('stdout', 'é')]
        assert result.stdout == result.stderr == ''
        assert len(result.tail) == 1
        result = await run_process([sys.executable, '-c',
            "import sys; sys.stderr.write('last'); sys.exit(3)"],
            on_line=line, accepted_exit_codes=(3,))
        assert result.returncode == 3 and lines[-1] == ('stderr', 'last')
        assert result.stderr == 'last'
        empty = await run_process([sys.executable, '-c',
                                   'import sys; print(repr(sys.argv[1]))', ''])
        assert empty.stdout.strip() == "''"
    asyncio.run(scenario())


@pytest.mark.parametrize('script,kwargs,code', [
    ("print('x'*100)", {'line_limit': 10}, 'output_limit'),
    ("import sys; sys.stdout.write('x'*100)", {'line_limit': 10}, 'output_limit'),
    ("print('x'*100)", {'output_limit': 10, 'capture': False}, 'output_limit'),
    ("import time; time.sleep(10)", {'timeout': .02}, 'tool_timeout'),
])
def test_stream_limits_and_timeout(script, kwargs, code):
    async def scenario():
        with pytest.raises(DomainError) as exc:
            await run_process([sys.executable, '-c', script], on_line=lambda *a: None, **kwargs)
        assert exc.value.code == code
    asyncio.run(scenario())


def test_callback_failure_reaps_child():
    async def scenario():
        pid = None
        def failed(stream, text):
            nonlocal pid
            pid = int(text)
            raise RuntimeError('parser failed')
        with pytest.raises(RuntimeError, match='parser failed'):
            await run_process([sys.executable, '-c',
                'import os,time; print(os.getpid(),flush=True); time.sleep(10)'], on_line=failed)
        if os.name == 'posix':
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
    asyncio.run(scenario())


def test_process_validation_and_missing_executable(tmp_path):
    async def scenario():
        for args, kwargs in [('', {}), ([''], {}), (['a'], {'line_limit': 0}),
                             (['a'], {'tail_chunks': -1}), (['a'], {'timeout': 0}),
                             (['a'], {'terminate_grace': float('nan')})]:
            with pytest.raises(ValueError):
                await run_process(args, **kwargs)
        with pytest.raises(DomainError) as exc:
            await run_process([str(tmp_path / 'missing')])
        assert exc.value.code == 'tool_launch_failed'
        result = await run_process([sys.executable, '-c', 'raise SystemExit(7)'],
                                   accepted_exit_codes=None, tail_chunks=0)
        assert result.returncode == 7 and result.tail == ()
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != 'posix', reason='POSIX signal escalation')
def test_graceful_stop_escalates_for_uncooperative_child():
    async def scenario():
        ready = asyncio.Event()
        pid = None
        def line(stream, text):
            nonlocal pid
            pid = int(text)
            ready.set()
        task = asyncio.create_task(run_process([sys.executable, '-c',
            'import signal,os,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
            'print(os.getpid(),flush=True); time.sleep(10)'], on_line=line, terminate_grace=.02))
        await asyncio.wait_for(ready.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    asyncio.run(scenario())
