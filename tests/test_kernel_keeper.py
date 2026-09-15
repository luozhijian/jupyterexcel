import asyncio
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from jupyterexcel.execution import SharedKernelExecutor
from jupyterexcel.kernel_keeper import KernelKeeper


class KeeperTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        manager = SimpleNamespace(cull_kernel_if_idle=AsyncMock(), shutdown_all=AsyncMock())
        executor = SimpleNamespace(manager=manager, kernel_id='excel', username='alice',
                                   ensure_ready=AsyncMock(return_value=True))
        keeper = KernelKeeper(executor, logging.getLogger('test'), interval=0.01)
        return manager, executor, keeper

    async def test_start_cull_exclusion_and_shutdown(self):
        manager, executor, keeper = self.make()
        cull, shutdown = manager.cull_kernel_if_idle, manager.shutdown_all
        keeper.install()
        # Scheduled startup requires no Excel request.
        for _ in range(20):
            if executor.ensure_ready.await_count:
                break
            await asyncio.sleep(0.01)
        self.assertGreater(executor.ensure_ready.await_count, 0)
        await manager.cull_kernel_if_idle('excel')
        cull.assert_not_awaited()
        await manager.cull_kernel_if_idle('other')
        cull.assert_awaited_once_with('other')
        await manager.shutdown_all(now=True)
        shutdown.assert_awaited_once_with(now=True)
        self.assertTrue(keeper.closed)
        self.assertIsNone(keeper.task)
        self.assertIs(manager.cull_kernel_if_idle, cull)
        count = executor.ensure_ready.await_count
        await asyncio.sleep(0.03)
        self.assertEqual(executor.ensure_ready.await_count, count)

    async def test_failure_backoff_and_success_reset(self):
        _, executor, keeper = self.make()
        keeper.interval, keeper.max_retry = 30, 60
        executor.ensure_ready.side_effect = [RuntimeError(), RuntimeError(), True, True]
        delays = []
        async def sleep(delay):
            delays.append(delay)
            if len(delays) == 4:
                keeper.closed = True
        with patch('jupyterexcel.kernel_keeper.asyncio.sleep', side_effect=sleep):
            await keeper._run()
        self.assertEqual(delays, [30, 60, 30, 30])

    async def test_busy_or_reserved_kernel_is_not_initialized(self):
        manager = SimpleNamespace(list_kernels=lambda: [{'id':'one','execution_state':'busy'}])
        executor = SharedKernelExecutor(manager, None, None, 'alice')
        executor.kernel_id = 'one'
        executor._initialize = AsyncMock()
        self.assertFalse(await executor.ensure_ready())
        async with executor.lock:
            self.assertFalse(await executor.ensure_ready())
        executor._initialize.assert_not_awaited()

    async def test_dead_process_is_replaced_and_initialized(self):
        models = [{'id':'old','execution_state':'idle'}]
        async def shutdown(kernel_id, now):
            self.assertEqual(kernel_id, 'old')
            models.clear()
        async def create(**kwargs):
            models.append({'id':'new','execution_state':'idle'})
            return {'kernel':{'id':'new'}}
        manager = SimpleNamespace(list_kernels=lambda: models,
            get_kernel=lambda key: SimpleNamespace(is_alive=AsyncMock(return_value=False)),
            shutdown_kernel=AsyncMock(side_effect=shutdown))
        sessions = SimpleNamespace(list_sessions=lambda: [], create_session=AsyncMock(side_effect=create))
        executor = SharedKernelExecutor(manager, sessions, None, 'alice')
        executor.kernel_id = 'old'
        executor._initialize = AsyncMock()
        self.assertTrue(await executor.ensure_ready())
        self.assertEqual(executor.kernel_id, 'new')
        executor._initialize.assert_awaited_once_with('new')


    async def test_extension_setting_is_opt_in_and_installs_once(self):
        import os
        import tempfile
        from unittest.mock import Mock
        from jupyterexcel.assets import AssetStore
        from jupyterexcel.server_extension import load_jupyter_server_extension
        for value in ('', '0', '1'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as root:
                app = SimpleNamespace(
                    log=logging.getLogger('test'),
                    kernel_manager=object(), session_manager=object(),
                    contents_manager=SimpleNamespace(register_post_save_hook=Mock()),
                    web_app=SimpleNamespace(settings={}, add_handlers=Mock()))
                with patch.dict(os.environ, {'JUPYTEREXCEL_ASSET_DIR':root,
                                             'JUPYTEREXCEL_KEEP_KERNEL_READY':value}), \
                     patch.object(AssetStore, 'schedule'), \
                     patch('jupyterexcel.kernel_keeper.KernelKeeper') as keeper:
                    load_jupyter_server_extension(app)
                    load_jupyter_server_extension(app)
                    if value == '1':
                        keeper.return_value.install.assert_called_once()
                        self.assertIn('jupyterexcel_kernel_keeper', app.web_app.settings)
                    else:
                        keeper.assert_not_called()
