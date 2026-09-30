"""Per-server adaptive pool; workers share code, never Python memory."""
import asyncio
from collections import deque
import math
import logging
import time
from types import SimpleNamespace

from .execution import ExecutionError, KernelExecutor, SharedKernelExecutor, resolved
from .discovery import read_project_config
from .kernel_connection import KernelConnection

DEFAULTS = dict(min_kernels=2, max_kernels=4, scale_up_utilization=0.8,
                utilization_window_seconds=5, queue_scale_up_after_seconds=1,
                queue_timeout_seconds=30, startup_timeout_seconds=60,
                max_queue_size=1000, scale_up_cooldown_seconds=1)


def execution_settings(config):
    supplied = config.get('execution', {})
    if not isinstance(supplied, dict) or set(supplied) - DEFAULTS.keys():
        raise ValueError('jupyterexcel-config.json: invalid execution settings.')
    settings = dict(DEFAULTS, **supplied)
    for key, value in settings.items():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError('execution.' + key + ' must be a positive finite number.')
    for key in ('min_kernels', 'max_kernels', 'max_queue_size'):
        if not isinstance(settings[key], int):
            raise ValueError('execution.' + key + ' must be an integer.')
    if settings['min_kernels'] > settings['max_kernels'] or settings['scale_up_utilization'] > 1:
        raise ValueError('Invalid kernel limits or utilization threshold.')
    return settings


class KernelPoolExecutor:
    def __init__(self, manager, sessions, contents, username, timeout=30):
        self.manager, self.sessions, self.contents = manager, sessions, contents
        self.username, self.timeout = username, timeout
        self.settings = dict(DEFAULTS)
        self.workers, self.queue = [], deque()
        self.snapshot = []
        self.closed = False
        self.reloading = False
        self.monitor = self.spawning = None
        self.tasks = set()
        self.start_lock, self.reload_lock = asyncio.Lock(), asyncio.Lock()
        self.last_error = None
        self.retry_at = self.last_spawn = 0
        self.serial = 0
        self._hooks = []

    async def start(self):
        async with self.start_lock:
            if self.closed:
                raise ExecutionError(503, 'pool_closed', 'Jupyter kernel pool is shutting down.')
            if self.monitor is not None:
                return
            config, _ = await read_project_config(self.contents)
            self.settings = execution_settings(config)
            self.snapshot = await SharedKernelExecutor(self.manager, self.sessions, self.contents, self.username)._notebooks()
            self.monitor = asyncio.create_task(self._maintain())

    def install(self, log):
        # Protect only this pool's workers from idle culling, never user notebooks.
        def hook(name, wrapper):
            had = name in vars(self.manager)
            old = getattr(self.manager, name)
            self._hooks.append((name, had, old))
            setattr(self.manager, name, wrapper(old))
        if hasattr(self.manager, 'cull_kernel_if_idle'):
            def cull_wrapper(original):
                async def cull(kernel_id, *args, **kwargs):
                    if any(w.kernel_id == kernel_id for w in self.workers):
                        return
                    return await resolved(original(kernel_id, *args, **kwargs))
                return cull
            hook('cull_kernel_if_idle', cull_wrapper)
        def shutdown_wrapper(original):
            async def shutdown(*args, **kwargs):
                await self.stop()
                return await resolved(original(*args, **kwargs))
            return shutdown
        hook('shutdown_all', shutdown_wrapper)
        async def boot():
            try:
                await self.start()
            except Exception:
                self.last_error = 'Pool startup failed; check project settings and the server log.'
                log.exception('JupyterExcel pool startup failed')
        from tornado.ioloop import IOLoop
        IOLoop.current().add_callback(boot)

    def utilization(self, worker, now):
        cutoff = now - self.settings['utilization_window_seconds']
        while worker.intervals and worker.intervals[0][1] <= cutoff:
            worker.intervals.popleft()
        total = sum(end - max(start, cutoff) for start, end in worker.intervals)
        if worker.busy_since is not None:
            total += now - max(worker.busy_since, cutoff)
        return min(1, total / self.settings['utilization_window_seconds'])

    def status(self):
        now = time.monotonic()
        serving = [w for w in self.workers if w.state in ('idle', 'busy')]
        queued = [r for r in self.queue if not r.result.done()]
        return dict(settings=dict(self.settings), queued_requests=len(queued),
                    oldest_wait_seconds=max((now - r.queued for r in queued), default=0),
                    utilization=sum(self.utilization(w, now) for w in serving) / max(1, len(serving)),
                    scaling_status='Reloading notebooks' if self.reloading else 'Starting a kernel' if self.spawning else 'Monitoring demand',
                    last_error=self.last_error,
                    kernels=[dict(name=w.name, kernel_id=w.kernel_id, status=w.state,
                                  utilization=self.utilization(w, now), current_function=w.function,
                                  completed_calls=w.completed, failed_calls=w.failed,
                                  startup_seconds=w.startup_seconds) for w in self.workers])

    async def _spawn(self):
        self.serial += 1
        engine = SharedKernelExecutor(self.manager, self.sessions, self.contents, self.username,
                                      timeout=self.settings['startup_timeout_seconds'])
        engine.connection = KernelConnection()
        snapshot = self.snapshot
        async def notebooks():
            return snapshot
        engine._notebooks = notebooks
        w = SimpleNamespace(engine=engine, name='Kernel ' + str(self.serial), kernel_id=None,
                            state='starting', intervals=deque(), busy_since=None, function=None,
                            completed=0, failed=0, startup_seconds=None)
        self.workers.append(w)
        started = time.monotonic()
        try:
            w.kernel_id = await engine._ensure_kernel()
            async def initialize():
                await engine._initialize(w.kernel_id)
                await self._wait_idle(w)
            await asyncio.wait_for(initialize(), self.settings['startup_timeout_seconds'])
            w.startup_seconds = time.monotonic() - started
            w.state = 'idle'
        except asyncio.CancelledError:
            w.kernel_id = w.kernel_id or engine.kernel_id
            await self._retire(w)
            raise
        except Exception:
            logging.getLogger(__name__).exception('Managed kernel initialization failed')
            w.kernel_id = w.kernel_id or engine.kernel_id
            self.last_error = 'Kernel initialization failed. Inspect notebook initialization and the server log.'
            self.retry_at = time.monotonic() + 30
            await self._retire(w)

    async def _retire(self, w):
        w.state = 'unavailable'
        w.engine.connection.close()
        try:
            if w.kernel_id:
                sessions = await resolved(self.sessions.list_sessions())
                session = next((s for s in sessions if s.get('kernel', {}).get('id') == w.kernel_id), None)
                if session and session.get('id') and hasattr(self.sessions, 'delete_session'):
                    await resolved(self.sessions.delete_session(session['id']))
                else:
                    models = await resolved(self.manager.list_kernels())
                    if any(m['id'] == w.kernel_id for m in models):
                        await resolved(self.manager.shutdown_kernel(w.kernel_id, now=True))
        except Exception:
            logging.getLogger(__name__).exception('Managed kernel cleanup failed')
            self.last_error = 'Could not clean up a managed kernel; check the server log.'
            return  # Retain ownership and count against max_kernels.
        if w in self.workers:
            self.workers.remove(w)

    async def _wait_idle(self, w):
        stable = 0
        while stable < 2:
            models = await resolved(self.manager.list_kernels())
            model = next((m for m in models if m['id'] == w.kernel_id), None)
            if model is None:
                raise ExecutionError(503, 'kernel_lost', 'The managed kernel stopped.')
            kernel = self.manager.get_kernel(w.kernel_id)
            if hasattr(kernel, 'is_alive') and not await resolved(kernel.is_alive()):
                raise ExecutionError(503, 'kernel_lost', 'The managed kernel stopped.')
            stable = stable + 1 if model.get('execution_state') == 'idle' else 0
            if stable < 2:
                await asyncio.sleep(0.1)

    async def _maintain(self):
        while not self.closed:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger(__name__).exception('Kernel pool maintenance failed')
                self.last_error = 'Pool maintenance failed; check the server log.'
            await asyncio.sleep(0.1)

    async def _tick(self):
        now = time.monotonic()
        if self.spawning is not None and self.spawning.done():
            self.spawning.result()
            self.spawning = None
        while self.queue and (self.queue[0].result.done() or now - self.queue[0].queued >= self.settings['queue_timeout_seconds']):
            request = self.queue.popleft()
            if not request.result.done():
                request.result.set_exception(ExecutionError(503, 'queue_timeout', 'Timed out waiting for an available Jupyter kernel.'))
        if self.reloading:
            return
        models = {m['id']: m for m in await resolved(self.manager.list_kernels())}
        if self.reloading or self.closed:
            return
        for w in list(self.workers):
            if w.state not in ('idle', 'busy'):
                continue
            kernel = self.manager.get_kernel(w.kernel_id) if w.kernel_id in models else None
            alive = kernel is not None and (not hasattr(kernel, 'is_alive') or await resolved(kernel.is_alive()))
            if not alive:
                if getattr(w, 'task', None) and not w.task.done():
                    w.task.cancel()
                    await asyncio.gather(w.task, return_exceptions=True)
                await self._retire(w)
        if self.reloading or self.closed:
            return
        # The reservation and removal happen without awaiting: one owner per worker.
        for w in self.workers:
            if not self.queue:
                break
            if w.state != 'idle' or models.get(w.kernel_id, {}).get('execution_state') != 'idle':
                continue
            request = self.queue.popleft()
            if request.result.done():
                continue
            w.state, w.busy_since, w.function = 'busy', now, request.function
            task = asyncio.create_task(self._serve(w, request))
            w.task = task
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        serving = [w for w in self.workers if w.state in ('idle', 'busy')]
        utilization = sum(self.utilization(w, now) for w in serving) / max(1, len(serving))
        queued = bool(self.queue) and now - self.queue[0].queued >= self.settings['queue_scale_up_after_seconds']
        available = any(w.state == 'idle' and models.get(w.kernel_id, {}).get('execution_state') == 'idle' for w in serving)
        pressure = (queued and not available) or utilization >= self.settings['scale_up_utilization']
        if self.spawning is None and len(self.workers) < self.settings['max_kernels'] and now >= self.retry_at:
            if len(self.workers) < self.settings['min_kernels'] or (pressure and now - self.last_spawn >= self.settings['scale_up_cooldown_seconds']):
                self.last_spawn = now
                self.spawning = asyncio.create_task(self._spawn())

    async def _serve(self, w, request):
        async def run():
            # Also reinitialize after an external restart; the snapshot is frozen.
            await w.engine._initialize(w.kernel_id)
            manager = SimpleNamespace(list_kernels=lambda: [{'id': w.kernel_id, 'execution_state': 'idle'}],
                                      get_kernel=lambda _: self.manager.get_kernel(w.kernel_id))
            return await KernelExecutor(manager, timeout=None, connection=w.engine.connection).execute(request.function, request.inputs, action=request.action)
        operation = asyncio.create_task(run())
        healthy = True
        try:
            try:
                result = await asyncio.wait_for(asyncio.shield(operation), self.timeout)
            except asyncio.TimeoutError:
                if not request.result.done():
                    request.result.set_exception(ExecutionError(504, 'timeout', 'Execution timed out; Python is still running. The kernel remains reserved.'))
                self.last_error = 'A function timed out; its kernel remains reserved until completion.'
                w.failed += 1
                # Keep the client and reservation alive until the actual reply.
                await operation
            else:
                w.completed += 1
                if not result.get('ok'):
                    w.failed += 1
                if not request.result.done():
                    request.result.set_result(result)
            await self._wait_idle(w)
        except asyncio.CancelledError:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            if not request.result.done():
                request.result.set_exception(ExecutionError(503, 'pool_closed', 'Jupyter kernel pool stopped.'))
            raise
        except Exception:
            logging.getLogger(__name__).exception('Managed kernel request failed')
            healthy = False
            w.failed += 1
            self.last_error = 'A kernel request failed; the affected worker is being replaced.'
            if not request.result.done():
                request.result.set_exception(ExecutionError(500, 'kernel_error', self.last_error))
            await self._retire(w)
        finally:
            if w.busy_since is not None:
                w.intervals.append((w.busy_since, time.monotonic()))
            w.busy_since, w.function = None, None
            if healthy and w in self.workers:
                w.state = 'idle'

    async def execute(self, function_id, inputs, idle_only=False, action=None):
        await self.start()
        if len(self.queue) >= self.settings['max_queue_size']:
            raise ExecutionError(503, 'queue_full', 'Jupyter request queue is full; try again later.')
        result = asyncio.get_running_loop().create_future()
        self.queue.append(SimpleNamespace(function=function_id, inputs=inputs, action=action,
                                          queued=time.monotonic(), result=result))
        return await result

    async def reload_notebook(self, path):
        await self.start()
        async with self.reload_lock:
            self.reloading = True
            try:
                async def drain():
                    if self.spawning:
                        await asyncio.shield(self.spawning)
                    while self.tasks or any(w.state == 'busy' for w in self.workers):
                        await asyncio.sleep(0.1)
                try:
                    await asyncio.wait_for(drain(), self.settings['queue_timeout_seconds'])
                except asyncio.TimeoutError:
                    raise ExecutionError(503, 'kernel_busy', 'Active calls are still running; retry notebook reload.') from None
                scanner = SharedKernelExecutor(self.manager, self.sessions, self.contents, self.username)
                snapshot = await scanner._notebooks()
                if not any(p == path for p, _ in snapshot):
                    raise ExecutionError(400, 'notebook_excluded', 'Include this notebook in discovery before reloading the pool.')
                for w in list(self.workers):
                    await self._retire(w)
                if self.workers:
                    raise ExecutionError(500, 'reload_failed', 'Old kernels could not be retired; restart the server before serving updated notebooks.')
                self.snapshot = snapshot
                self.retry_at = 0
                self.spawning = asyncio.create_task(self._spawn())
                await asyncio.shield(self.spawning)
                ready = next((w for w in self.workers if w.state == 'idle'), None)
                if ready is None:
                    raise ExecutionError(500, 'reload_failed', 'Could not initialize the updated notebooks.')
                return ready.kernel_id
            finally:
                self.reloading = False

    async def stop(self):
        self.closed = True
        for request in self.queue:
            if not request.result.done():
                request.result.set_exception(ExecutionError(503, 'pool_closed', 'Jupyter kernel pool stopped.'))
        self.queue.clear()
        tasks = [t for t in (self.monitor, self.spawning, *self.tasks) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for w in list(self.workers):
            await self._retire(w)
        for name, had, original in self._hooks:
            if had:
                setattr(self.manager, name, original)
            else:
                delattr(self.manager, name)
        self._hooks.clear()
