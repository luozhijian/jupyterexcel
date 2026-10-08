"""Route exported functions to explicit environment pools."""
import asyncio
import hashlib
import json
from .execution import ExecutionError, resolved
from .kernel_pool import KernelPoolExecutor
from .profile_pool import KernelBudget, ProfilePool
from .profiles import validate_profiles, ProfileWarnings


class ProfileExecutor:
    def __init__(self, manager, sessions, contents, username, execution):
        self.manager, self.sessions, self.contents = manager, sessions, contents
        self.profile_warnings = ProfileWarnings()
        self.profiles, self.defaults, total = validate_profiles(execution)
        self.legacy_mode = not any(key in execution for key in ('profiles', 'defaults', 'default_profiles', 'total_max_kernels'))
        self.legacy = KernelPoolExecutor(manager, sessions, contents, username, execution.get('timeout_seconds', 30)) if self.legacy_mode else None
        self.budget = KernelBudget(total, lambda: len(self.legacy.workers) if self.legacy else 0)
        self.pools = {name: ProfilePool(name, profile, manager, contents, self.budget)
                      for name, profile in self.profiles.items() if profile['enabled'] and not (self.legacy and name == 'python-default')}
        if self.legacy:
            self.legacy.capacity_available = lambda: self.budget.used + len(self.legacy.workers) < total
        async def reclaim():
            for pool in self.pools.values():
                if len(pool.workers) > pool.settings['min_kernels']:
                    worker = next((w for w in pool.workers if w.state == 'idle'), None)
                    if worker:
                        worker.state = 'retiring'
                        await pool._retire(worker)
                        return
        self.budget.reclaim = reclaim
        self.closed, self._hooks = False, []

    async def catalog(self):
        from .discovery import selected_notebooks
        from .office_addin import scan_notebook
        found = {}
        for path, model in await selected_notebooks(self.contents):
            notebook = model['content']
            functions = await asyncio.to_thread(scan_notebook, notebook, path)
            metadata = notebook.get('metadata', {})
            identity = [[ ''.join(c.get('source', '')) for c in notebook.get('cells', []) if c.get('cell_type') == 'code'],
                        metadata.get('kernelspec', {}), metadata.get('jupyterexcel', {})]
            revision = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            for function in functions:
                if function.kind == 'ribbon' and not function.action:
                    continue
                key = function.function_id.casefold()
                if key in found:
                    raise ValueError('Duplicate exported function: ' + function.function_id)
                name = self.profile_warnings.resolve(function, notebook, self.profiles, self.defaults, self.legacy_mode) if function.execution == 'server' else None
                found[key] = (function, notebook, name, revision)
        return found

    async def start(self):
        if self.closed:
            return
        if self.legacy:
            await self.legacy.start()
        for pool in self.pools.values():
            await pool.start()

    def install(self, log):
        def hook(name, wrapper):
            if not hasattr(self.manager, name):
                return
            original = getattr(self.manager, name)
            self._hooks.append((name, name in vars(self.manager), original))
            setattr(self.manager, name, wrapper(original))
        def shutdown(original):
            async def run(*args, **kwargs):
                await self.stop()
                return await resolved(original(*args, **kwargs))
            return run
        def cull(original):
            async def run(kernel_id, *args, **kwargs):
                owned = {w.id for p in self.pools.values() for w in p.workers}
                if self.legacy:
                    owned.update(w.kernel_id for w in self.legacy.workers)
                if kernel_id not in owned:
                    from .execution import resolved
                    return await resolved(original(kernel_id, *args, **kwargs))
            return run
        hook('shutdown_all', shutdown)
        hook('cull_kernel_if_idle', cull)
        async def boot():
            try:
                await self.start()
            except Exception:
                log.exception('Execution profile startup failed')
        from tornado.ioloop import IOLoop
        IOLoop.current().add_callback(boot)

    async def execute_version(self, function_id, inputs, idle_only=False, action=None, version=None):
        if self.closed:
            raise ExecutionError(503, 'pool_closed', 'Execution pools stopped.')
        try:
            entry = (await self.catalog()).get(function_id.casefold())
        except ValueError as error:
            raise ExecutionError(400, 'execution_profile', str(error)) from error
        if entry is None:
            raise ExecutionError(404, 'function_not_found', 'Unknown exported function: ' + function_id)
        function, notebook, name, revision = entry
        if function.execution == 'local':
            raise ExecutionError(400, 'local_function', 'This function runs in the Excel add-in.')
        if action is False and function.kind == 'ribbon':
            raise ExecutionError(405, 'action_requires_post', 'Ribbon actions require POST.')
        if version and function.language == 'javascript' and version != function.version:
            raise ExecutionError(409, 'stale_export', 'Notebook changed. Reload the Excel add-in.')
        if self.legacy and name == 'python-default':
            return await self.legacy.execute(function_id, inputs, idle_only=idle_only, action=action)
        return await self.pools[name].execute(function, notebook, inputs, action, version, revision)

    async def execute(self, function_id, inputs, idle_only=False, action=None):
        return await self.execute_version(function_id, inputs, idle_only, action)

    async def reload_notebook(self, path):
        catalog = await self.catalog()
        entries = [entry for entry in catalog.values() if entry[0].notebook == path and entry[2]]
        if not entries:
            # A local-only notebook needs asset regeneration but no kernel.
            if any(entry[0].notebook == path for entry in catalog.values()):
                return None
            raise ExecutionError(400, 'notebook_excluded', 'No server exports in this notebook.')
        if self.legacy and any(entry[2] == 'python-default' for entry in entries):
            return await self.legacy.reload_notebook(path)
        for name in {entry[2] for entry in entries}:
            await self.pools[name].reload(path)
        return None

    def status(self):
        profiles = [pool.status() for pool in self.pools.values()]
        if self.legacy:
            legacy = self.legacy.status()
            profiles.insert(0, dict(legacy, profile='python-default'))
        kernels = [dict(kernel, name=profile['profile'] + ' / ' + (kernel.get('notebook') or kernel['name']),
                        profile=profile['profile']) for profile in profiles for kernel in profile['kernels']]
        return dict(settings=dict(max_kernels=self.budget.limit, utilization_window_seconds=5),
                    kernels=kernels, profiles=profiles,
                    queued_requests=sum(p['queued_requests'] for p in profiles),
                    oldest_wait_seconds=max((p['oldest_wait_seconds'] for p in profiles), default=0),
                    utilization=sum(k['utilization'] for k in kernels) / max(1, len(kernels)),
                    scaling_status='Monitoring execution profiles',
                    last_error='; '.join(p['last_error'] for p in profiles if p.get('last_error')) or None)

    async def stop(self):
        self.closed = True
        await asyncio.gather(*(pool.stop() for pool in self.pools.values()))
        if self.legacy:
            await self.legacy.stop()
        for name, had, original in self._hooks:
            if had:
                setattr(self.manager, name, original)
            else:
                delattr(self.manager, name)
        self._hooks.clear()
