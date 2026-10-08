"""Notebook-isolated workers with profile and server-wide capacity limits."""
import asyncio
import time
import uuid
from collections import deque
from types import SimpleNamespace
from .execution import ExecutionError, SharedKernelExecutor, KernelExecutor, resolved
from .kernel_connection import KernelConnection
from .javascript_execution import JavaScriptExecutor


class KernelBudget:
    def __init__(self, limit, legacy_count=lambda: 0):
        self.limit, self.legacy_count, self.used = limit, legacy_count, 0

    def reserve(self):
        if self.used + self.legacy_count() >= self.limit:
            return False
        self.used += 1
        return True

    def release(self):
        self.used -= 1


class ProfileWorker:
    def __init__(self, pool):
        self.pool = pool
        self.id = self.client = self.connection = self.transport = self.engine = None
        self.path = self.version = None
        self.state, self.function = 'starting', None
        self.used = time.monotonic()
        self.completed = self.failed = 0
        self.startup_seconds = None
        self.intervals, self.busy_since = deque(), None

    async def start(self):
        pool = self.pool
        started = time.monotonic()
        # Resolve using registered kernelspec names; never use display names or a shell command.
        spec = pool.manager.kernel_spec_manager.get_kernel_spec(pool.settings['kernel_name'])
        aliases = {'python': 'python', 'javascript': 'javascript', 'typescript': 'javascript', 'r': 'r'}
        if aliases.get(spec.language.lower()) != pool.settings['language']:
            raise ValueError('Kernelspec language does not match execution profile ' + pool.name)
        self.id = uuid.uuid4().hex
        await resolved(pool.manager.start_kernel(kernel_name=pool.settings['kernel_name'], kernel_id=self.id))
        kernel = pool.manager.get_kernel(self.id)
        if pool.settings['language'] == 'python':
            self.connection = KernelConnection()
            self.client = self.connection.open(kernel)
            await self.connection.wait_for_ready(pool.settings['startup_timeout_seconds'])
            self.engine = SharedKernelExecutor(pool.manager, None, pool.contents, pool.name,
                                              timeout=pool.settings['startup_timeout_seconds'])
            self.engine.connection = self.connection
        else:
            self.transport = JavaScriptExecutor(pool.manager, pool.contents, pool.settings['timeout_seconds'])
            self.client = kernel.client()
            self.client.start_channels()
            await self.client.wait_for_ready(timeout=pool.settings['startup_timeout_seconds'])
        self.startup_seconds = time.monotonic() - started

    async def initialize(self, function, notebook, version):
        self.path, self.version = function.notebook, version
        cells = [(i, ''.join(c.get('source', ''))) for i, c in enumerate(notebook.get('cells', []), 1)
                 if c.get('cell_type') == 'code']
        if self.engine:
            async def selected():
                return [(self.path, cells)]
            self.engine._notebooks = selected
            await self.engine._initialize(self.id)
        else:
            for _, source in cells:
                await self.transport._run(self.client, source)
            self.transport.workers[self.path] = {'id': self.id, 'client': self.client, 'version': function.version}
            async def bound_worker(*args):
                if not await resolved(self.pool.manager.get_kernel(self.id).is_alive()):
                    raise ExecutionError(503, 'kernel_lost', 'The profile kernel stopped.')
                return self.transport.workers[self.path]
            # Only the pool may spawn; recovery must not bypass its environment or budget.
            self.transport._worker = bound_worker

    async def execute(self, function, notebook, inputs, action, version):
        if self.engine:
            await self.engine._initialize(self.id)
            manager = SimpleNamespace(list_kernels=lambda: [{'id': self.id, 'execution_state': 'idle'}],
                                      get_kernel=lambda _: self.pool.manager.get_kernel(self.id))
            return await KernelExecutor(manager, timeout=None, connection=self.connection).execute(
                function.function_id, inputs, action=action)
        return await self.transport.execute(function.function_id, inputs, action=action, version=version,
                                            entry=(function, notebook))

    async def close(self):
        if self.connection:
            self.connection.close()
        elif self.client:
            self.client.stop_channels()
        if self.id:
            from tornado.web import HTTPError
            try:
                await resolved(self.pool.manager.shutdown_kernel(self.id, now=True))
            except KeyError:
                pass
            except HTTPError as error:
                if error.status_code != 404:
                    raise


class ProfilePool:
    def __init__(self, name, settings, manager, contents, budget):
        self.name, self.settings = name, settings
        self.manager, self.contents, self.budget = manager, contents, budget
        self.workers, self.requests, self.tasks = [], {}, set()
        self.closed, self.monitor = False, None
        self.last_error, self.retry_at = None, 0
        self.last_spawn = 0

    async def start(self):
        if self.closed:
            raise ExecutionError(503, 'pool_closed', 'Execution profile stopped.')
        if self.monitor is None:
            self.monitor = asyncio.create_task(self._maintain())

    async def _retire(self, worker):
        worker.state = 'unavailable'
        try:
            await worker.close()
        except Exception as error:
            self.last_error = 'Kernel cleanup failed: ' + str(error)
            return
        if worker in self.workers:
            self.workers.remove(worker)
            self.budget.release()

    def _allocate(self):
        if self.closed or len(self.workers) >= self.settings['max_kernels'] or not self.budget.reserve():
            return None
        worker = ProfileWorker(self)
        self.workers.append(worker)
        self.last_spawn = time.monotonic()
        return worker

    async def _boot(self, worker):
        try:
            await asyncio.wait_for(worker.start(), self.settings['startup_timeout_seconds'])
            self.last_error, self.retry_at = None, 0
        except BaseException as error:
            self.last_error = 'Cannot start profile ' + self.name + ': ' + str(error)
            self.retry_at = time.monotonic() + 30
            await self._retire(worker)
            raise

    async def _maintain(self):
        while not self.closed:
            try:
                now = time.monotonic()
                for worker in list(self.workers):
                    if worker.state == 'idle' and len(self.workers) > self.settings['min_kernels'] and now - worker.used >= self.settings['idle_shutdown_seconds']:
                        worker.state = 'retiring'
                        await self._retire(worker)
                busy = [self.utilization(w, now) for w in self.workers]
                pressure = bool(busy) and sum(busy) / len(busy) >= self.settings['scale_up_utilization']
                if (len(self.workers) < self.settings['min_kernels'] or
                    (pressure and now - self.last_spawn >= self.settings['scale_up_cooldown_seconds'])) and now >= self.retry_at:
                    worker = self._allocate()
                    if worker:
                        await self._boot(worker)
                        worker.used = time.monotonic()
                        worker.state = 'idle'
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.last_error = str(error)
            await asyncio.sleep(.1)

    async def _acquire(self, function, notebook, revision):
        started = time.monotonic()
        while not self.closed:
            now = time.monotonic()
            if now - started >= self.settings['queue_timeout_seconds']:
                raise ExecutionError(503, 'queue_timeout', 'No available kernel for profile ' + self.name)
            worker = next((w for w in self.workers if w.state == 'idle' and (w.path is None or
                          (w.path == function.notebook and w.version == revision))), None)
            if worker:
                worker.state = 'busy'
                try:
                    if worker.path is None:
                        await asyncio.wait_for(worker.initialize(function, notebook, revision), self.settings['startup_timeout_seconds'])
                    return worker
                except BaseException:
                    await self._retire(worker)
                    raise
            if now < self.retry_at:
                raise ExecutionError(503, 'profile_unavailable', self.last_error or 'Profile startup is backing off.')
            delay = not self.workers or (now - started >= self.settings['queue_scale_up_after_seconds'] and
                                         now - self.last_spawn >= self.settings['scale_up_cooldown_seconds'])
            if delay:
                # An idle kernel initialized for another notebook cannot share its namespace.
                incompatible = next((w for w in self.workers if w.state == 'idle'), None)
                if incompatible:
                    incompatible.state = 'retiring'
                    await self._retire(incompatible)
                worker = self._allocate()
                if worker is None and hasattr(self.budget, 'reclaim'):
                    await self.budget.reclaim()
                    worker = self._allocate()
                if worker:
                    try:
                        await self._boot(worker)
                        await asyncio.wait_for(worker.initialize(function, notebook, revision), self.settings['startup_timeout_seconds'])
                        worker.state = 'busy'
                        return worker
                    except BaseException:
                        await self._retire(worker)
                        raise
            await asyncio.sleep(.05)
        raise ExecutionError(503, 'pool_closed', 'Execution profile stopped.')

    async def execute(self, function, notebook, inputs, action, version, revision):
        if self.closed:
            raise ExecutionError(503, 'pool_closed', 'Execution profile stopped.')
        if len(self.requests) >= self.settings['max_queue_size']:
            raise ExecutionError(503, 'queue_full', 'Execution profile queue is full.')
        await self.start()
        task = asyncio.current_task()
        self.requests[task] = time.monotonic()
        self.tasks.add(task)
        worker = None
        try:
            worker = await self._acquire(function, notebook, revision)
            self.requests.pop(task, None)
            worker.function = function.function_id
            worker.busy_since = time.monotonic()
            try:
                result = await asyncio.wait_for(worker.execute(function, notebook, inputs, action, version), self.settings['timeout_seconds'])
                worker.completed += 1
                if not result.get('ok'):
                    worker.failed += 1
                return result
            except BaseException:
                worker.failed += 1
                await self._retire(worker)
                raise
            finally:
                worker.function, worker.used = None, time.monotonic()
                worker.intervals.append((worker.busy_since, worker.used))
                worker.busy_since = None
                if worker in self.workers and worker.state != 'unavailable':
                    worker.state = 'idle'
        except asyncio.TimeoutError:
            raise ExecutionError(504, 'timeout', 'Execution profile timed out; its worker was retired. No retry was performed.') from None
        except (ExecutionError, asyncio.CancelledError):
            raise
        except Exception as error:
            self.last_error = str(error)
            raise ExecutionError(503, 'profile_error', 'Profile ' + self.name + ': ' + str(error)) from error
        finally:
            self.requests.pop(task, None)
            self.tasks.discard(task)

    async def reload(self, path):
        if any(w.path == path and w.state != 'idle' for w in self.workers):
            raise ExecutionError(503, 'kernel_busy', 'Notebook calls are running; retry reload.')
        for worker in list(self.workers):
            if worker.path == path:
                worker.state = 'retiring'
                await self._retire(worker)

    async def stop(self):
        self.closed = True
        tasks = [task for task in [self.monitor, *self.tasks] if task and task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for worker in list(self.workers):
            await self._retire(worker)

    def status(self):
        now = time.monotonic()
        return dict(profile=self.name, settings=self.settings, queued_requests=len(self.requests),
                    oldest_wait_seconds=max((now - value for value in self.requests.values()), default=0),
                    last_error=self.last_error, kernels=[dict(name=self.name, profile=self.name, notebook=w.path,
                        kernel_id=w.id, status=w.state, utilization=self.utilization(w, now),
                        current_function=w.function, completed_calls=w.completed, failed_calls=w.failed,
                        startup_seconds=w.startup_seconds) for w in self.workers])

    def utilization(self, worker, now):
        window = self.settings['utilization_window_seconds']
        cutoff = now - window
        while worker.intervals and worker.intervals[0][1] <= cutoff:
            worker.intervals.popleft()
        duration = sum(end - max(start, cutoff) for start, end in worker.intervals)
        if worker.busy_since is not None:
            duration += now - max(worker.busy_since, cutoff)
        return min(1, duration / window)
