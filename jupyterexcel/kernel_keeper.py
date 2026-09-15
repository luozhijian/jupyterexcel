"""Opt-in maintenance of one server's managed Excel kernel."""
import asyncio
from .execution import resolved


class KernelKeeper:
    """Keep the managed kernel ready without changing other kernels' policies."""

    def __init__(self, executor, log, interval=30, max_retry=300):
        self.executor, self.log = executor, log
        self.interval, self.max_retry = interval, max_retry
        self.task = None
        self.closed = False
        self.ready_id = None
        self._originals = {}
        self._wrappers = {}

    def install(self):
        manager = self.executor.manager
        # Per-instance hooks only: preserve shutdown and idle-culling of other kernels.
        original_cull = getattr(manager, 'cull_kernel_if_idle', None)
        if original_cull is not None:
            async def cull(kernel_id, *args, **kwargs):
                if not self.closed and kernel_id == self.executor.kernel_id:
                    return
                return await resolved(original_cull(kernel_id, *args, **kwargs))
            self._hook('cull_kernel_if_idle', cull)
        else:
            self.log.warning('JupyterExcel: kernel manager has no idle-culling hook; '
                             'verify its custom idle-shutdown policy.')
        original_shutdown = manager.shutdown_all

        async def shutdown(*args, **kwargs):
            await self.stop()
            return await resolved(original_shutdown(*args, **kwargs))
        self._hook('shutdown_all', shutdown)
        from tornado.ioloop import IOLoop
        IOLoop.current().add_callback(self.start)

    def _hook(self, name, wrapper):
        manager = self.executor.manager
        # Restore an inherited method by removing the instance override.
        self._originals[name] = (name in vars(manager), vars(manager).get(name))
        self._wrappers[name] = wrapper
        setattr(manager, name, wrapper)

    def start(self):
        if not self.closed and self.task is None:
            self.task = asyncio.create_task(self._run())

    async def stop(self):
        self.closed = True
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        manager = self.executor.manager
        for name, (had_override, original) in self._originals.items():
            if getattr(manager, name) is self._wrappers[name]:
                if had_override:
                    setattr(manager, name, original)
                else:
                    delattr(manager, name)
        self._originals.clear()
        self._wrappers.clear()

    async def _run(self):
        delay = self.interval
        while not self.closed:
            try:
                ready = await self.executor.ensure_ready()
                if ready and self.ready_id != self.executor.kernel_id:
                    self.ready_id = self.executor.kernel_id
                    self.log.info('JupyterExcel kernel ready: %s (user %s)',
                                  self.ready_id, self.executor.username)
                delay = self.interval
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Keep a failed notebook for inspection; do not repeatedly recreate it.
                self.log.warning('JupyterExcel keep-ready failed (%s); retrying in %s seconds. '
                                 'For notebook errors, fix the notebook and restart its kernel.',
                                 type(error).__name__, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_retry)
                continue
            await asyncio.sleep(delay)
