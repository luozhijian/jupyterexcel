import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from jupyterexcel.execution import ExecutionError, SharedKernelExecutor, KernelExecutor
from jupyterexcel.kernel_pool import KernelPoolExecutor, execution_settings


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.models, self.sessions = [], []
        self.next_id = 0
        async def create(**kwargs):
            self.next_id += 1
            ident = str(self.next_id)
            self.models.append({'id': ident, 'execution_state': 'idle'})
            session = dict(kwargs, id='s' + ident, kernel={'id': ident})
            self.sessions.append(session)
            return session
        async def delete(ident):
            session = next(s for s in self.sessions if s['id'] == ident)
            self.models[:] = [m for m in self.models if m['id'] != session['kernel']['id']]
            self.sessions.remove(session)
        self.manager = SimpleNamespace(list_kernels=lambda: self.models, get_kernel=lambda _: SimpleNamespace(is_alive=lambda: True))
        self.sm = SimpleNamespace(list_sessions=lambda: self.sessions, create_session=create, delete_session=delete)
        self.cm = SimpleNamespace(get=lambda *a, **kw: {'type':'directory', 'content':[]})
        self.pool = KernelPoolExecutor(self.manager, self.sm, self.cm, 'test', timeout=1)
        self.initialize = patch.object(SharedKernelExecutor, '_initialize', new=AsyncMock())
        self.initialize.start()
        await self.pool.start()
        self.pool.settings.update(min_kernels=1, max_kernels=1)

    async def asyncTearDown(self):
        await self.pool.stop()
        self.initialize.stop()

    async def until(self, predicate):
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(.01)

    async def test_minimum_workers_and_status(self):
        self.pool.settings.update(min_kernels=2, max_kernels=4)
        await self.until(lambda: len(self.pool.workers) == 2 and all(w.state == 'idle' for w in self.pool.workers))
        status = self.pool.status()
        self.assertEqual(len(status['kernels']), 2)
        self.assertEqual(status['settings']['utilization_window_seconds'], 5)
        self.assertEqual(status['queued_requests'], 0)

    async def test_burst_scales_and_concurrent_calls_use_distinct_workers(self):
        self.pool.settings.update(max_kernels=2, queue_scale_up_after_seconds=.05, scale_up_cooldown_seconds=.01)
        gate = asyncio.Event()
        active = set()
        async def execute(executor, *a, **kw):
            ident = executor.manager.list_kernels()[0]['id']
            self.assertNotIn(ident, active)
            active.add(ident)
            await gate.wait()
            active.remove(ident)
            return {'ok':True, 'result':1}
        with patch.object(KernelExecutor, 'execute', execute):
            requests = [asyncio.create_task(self.pool.execute('Sum', [1])) for _ in range(2)]
            await self.until(lambda: len(active) == 2)
            self.assertEqual(len(self.pool.workers), 2)
            gate.set()
            self.assertEqual([v['result'] for v in await asyncio.gather(*requests)], [1,1])

    async def test_timeout_keeps_worker_reserved_until_real_completion(self):
        self.pool.timeout = .05
        gate = asyncio.Event()
        started = asyncio.Event()
        async def execute(*a, **kw):
            started.set()
            await gate.wait()
            return {'ok':True, 'result':1}
        with patch.object(KernelExecutor, 'execute', execute):
            with self.assertRaises(ExecutionError) as error:
                await self.pool.execute('Slow', [])
            self.assertEqual(error.exception.code, 'timeout')
            self.assertEqual(self.pool.workers[0].state, 'busy')
            queued = asyncio.create_task(self.pool.execute('Next', []))
            await asyncio.sleep(.15)
            self.assertFalse(queued.done())
            gate.set()
            self.assertTrue((await queued)['ok'])

    async def test_queue_timeout_and_shutdown(self):
        self.pool.settings['queue_timeout_seconds'] = .05
        self.pool.reloading = True
        with self.assertRaises(ExecutionError) as error:
            await self.pool.execute('Queued', [])
        self.assertEqual(error.exception.code, 'queue_timeout')
        await self.pool.stop()
        self.assertEqual(self.models, [])

    async def test_queue_limit(self):
        self.pool.reloading = True
        self.pool.settings['max_queue_size'] = 1
        first = asyncio.create_task(self.pool.execute('One', []))
        await asyncio.sleep(0)
        with self.assertRaises(ExecutionError) as error:
            await self.pool.execute('Two', [])
        self.assertEqual(error.exception.code, 'queue_full')
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)

    async def test_reload_drains_and_replaces_all_workers(self):
        await self.until(lambda: self.pool.workers and self.pool.workers[0].state == 'idle')
        old = self.pool.workers[0].kernel_id
        with patch.object(SharedKernelExecutor, '_notebooks', AsyncMock(return_value=[('a.ipynb', [])])):
            new = await self.pool.reload_notebook('a.ipynb')
        self.assertNotEqual(old, new)
        self.assertNotIn(old, [m['id'] for m in self.models])
        self.assertEqual(self.pool.snapshot, [('a.ipynb', [])])

    def test_settings_validation(self):
        for values in ({'min_kernels':5}, {'max_kernels':True}, {'utilization_window_seconds':0}, {'scale_up_utilization':1.1}, {'unexpected':2}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                execution_settings({'execution':values})

    async def test_sustained_utilization_scales_without_a_queue(self):
        import time
        self.pool.settings.update(max_kernels=2, scale_up_cooldown_seconds=.01)
        await self.until(lambda: self.pool.workers and self.pool.workers[0].state == 'idle')
        now = time.monotonic()
        self.pool.workers[0].intervals.append((now - 4.5, now))
        await self.until(lambda: len(self.pool.workers) == 2)
        self.assertGreater(self.pool.status()['kernels'][0]['utilization'], .8)

    async def test_failed_initialization_backs_off(self):
        await self.until(lambda: self.pool.workers and self.pool.workers[0].state == 'idle')
        self.pool.settings.update(min_kernels=2, max_kernels=2)
        with patch.object(SharedKernelExecutor, '_initialize', AsyncMock(side_effect=RuntimeError('test initialization failure'))):
            await self.until(lambda: self.pool.retry_at > 0)
            attempts = self.next_id
            await asyncio.sleep(.25)
            self.assertEqual(self.next_id, attempts)
        self.assertEqual(len(self.pool.workers), 1)
        self.assertIn('initialization failed', self.pool.last_error)

    async def test_lifecycle_protects_only_owned_kernels_and_restores_hooks(self):
        import logging
        original_cull = AsyncMock()
        original_shutdown = AsyncMock()
        self.manager.cull_kernel_if_idle = original_cull
        self.manager.shutdown_all = original_shutdown
        await self.until(lambda: self.pool.workers and self.pool.workers[0].state == 'idle')
        self.pool.install(logging.getLogger('test'))
        await self.manager.cull_kernel_if_idle(self.pool.workers[0].kernel_id)
        original_cull.assert_not_awaited()
        await self.manager.cull_kernel_if_idle('user-notebook')
        original_cull.assert_awaited_once_with('user-notebook')
        await self.manager.shutdown_all(now=True)
        original_shutdown.assert_awaited_once_with(now=True)
        self.assertTrue(self.pool.closed)
        self.assertEqual(self.models, [])
        self.assertIs(self.manager.cull_kernel_if_idle, original_cull)
        self.assertIs(self.manager.shutdown_all, original_shutdown)
