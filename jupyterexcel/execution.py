"""Per-server kernel selection and JSON worksheet execution."""
import asyncio
import ast
import inspect
import json
import uuid


class ExecutionError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


async def resolved(value):
    return await value if inspect.isawaitable(value) else value


def invoke_export(function_id, inputs, action=None):
    """Runs inside the kernel; never evaluate a caller-supplied expression."""
    from IPython import get_ipython
    namespace = get_ipython().user_ns
    matches = {}
    for value in list(namespace.values()):
        metadata = getattr(value, '__jupyterexcel_action__', None) if action is not False else None
        metadata = metadata or (getattr(value, '__jupyterexcel_function__', None) if action is not True else None)
        if callable(value) and isinstance(metadata, dict):
            name = metadata.get('id', '')
            normalized = ''.join(c if c.isascii() and (c.isalnum() or c == '.') else '.' for c in name).upper().strip('.')
            if normalized == function_id.upper():
                matches[id(value)] = value
    if len(matches) != 1:
        return json.dumps({'ok': False, 'error': {'code': 'function_not_found' if not matches else 'duplicate_function', 'message': 'Expected one exported function in the selected kernel.'}})
    function = next(iter(matches.values()))
    action = isinstance(getattr(function, "__jupyterexcel_action__", None), dict)
    try:
        if action:
            from .actions import validate_inputs
            validate_inputs(function.__jupyterexcel_action__, inputs)
        inspect.signature(function).bind(*inputs)
    except (TypeError, ValueError) as error:
        return json.dumps({'ok': False, 'error': {'code': 'invalid_arguments', 'message': str(error)}})
    try:
        result = function(*inputs)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TypeError('Async worksheet functions are not supported in this version.')
        if action:
            from .actions import validate_result
            validate_result(function.__jupyterexcel_action__, result)
        return json.dumps({'ok': True, 'result': result}, allow_nan=False)
    except Exception as error:
        return json.dumps({'ok': False, 'error': {'code': 'execution_failed', 'message': str(error)}})


def invoke_action(function_id, inputs):
    return invoke_export(function_id, inputs, action=True)


class KernelExecutor:
    def __init__(self, manager, timeout=30):
        self.manager, self.timeout = manager, timeout
        self.reserved = set()
        self.lock = asyncio.Lock()

    async def execute(self, function_id, inputs, idle_only=False, action=None):
        async with self.lock:
            models = await resolved(self.manager.list_kernels())
            eligible = [m for m in models if not idle_only or m.get('execution_state') == 'idle']
            if not eligible:
                raise ExecutionError(503, 'no_kernel', 'No idle kernel available.' if idle_only else 'No kernel available.')
            # Single-user mode means first available, not first unreserved.
            candidates = eligible if idle_only else eligible[:1]
            selected = next((m for m in candidates if m['id'] not in self.reserved), None)
            if selected is None:
                raise ExecutionError(503, 'kernel_busy', 'The selected kernels are handling another Excel request.')
            kernel_id = selected['id']
            self.reserved.add(kernel_id)
        client = None
        try:
            kernel = self.manager.get_kernel(kernel_id)
            from jupyter_client import AsyncKernelClient
            client = AsyncKernelClient()
            client.load_connection_info(kernel.get_connection_info())
            client.start_channels()
            # Literal JSON decoding prevents input strings from becoming Python code.
            expression = "__import__('jupyterexcel.execution', fromlist=['invoke_export']).invoke_export(%r, __import__('json').loads(%r))" % (function_id, json.dumps(inputs, allow_nan=False))
            if action is False:
                expression = expression[:-1] + ", action=False)"
            if action is True:
                expression = expression.replace("fromlist=['invoke_export']).invoke_export(", "fromlist=['invoke_action']).invoke_action(")
            message_id = client.execute('', silent=True, store_history=False,
                                        user_expressions={'excel': expression}, allow_stdin=False)
            async def reply():
                while True:
                    message = await client.get_shell_msg()
                    if message.get('parent_header', {}).get('msg_id') == message_id:
                        content = message['content']
                        value = content.get('user_expressions', {}).get('excel', {})
                        if content.get('status') != 'ok' or value.get('status') != 'ok':
                            raise ExecutionError(500, 'kernel_error', 'Kernel could not evaluate the worksheet function.')
                        return json.loads(ast.literal_eval(value['data']['text/plain']))
            return await asyncio.wait_for(reply(), self.timeout)
        except asyncio.TimeoutError:
            raise ExecutionError(504, 'timeout', 'Execution timed out; the kernel may still be running the function.') from None
        finally:
            if client is not None:
                client.stop_channels()
            self.reserved.discard(kernel_id)


class SharedKernelExecutor:
    """One managed, named session per server; notebook state is shared."""

    def __init__(self, manager, sessions, contents, username, timeout=30):
        self.manager, self.sessions, self.contents = manager, sessions, contents
        self.username, self.timeout = username, timeout
        self.kernel_id = None
        self.number = 0
        self.lock = asyncio.Lock()

    async def ensure_ready(self):
        """Initialize/recover without a worksheet request; never interrupt busy work."""
        # Avoid building a queue behind worksheet calls.
        if self.lock.locked():
            return False
        async with self.lock:
            if self.kernel_id:
                models = await resolved(self.manager.list_kernels())
                model = next((m for m in models if m['id'] == self.kernel_id), None)
                if model and model.get('execution_state') == 'busy':
                    return False
                if model:
                    kernel = self.manager.get_kernel(self.kernel_id)
                    if not await resolved(kernel.is_alive()):
                        await resolved(self.manager.shutdown_kernel(self.kernel_id, now=True))
                        self.kernel_id = None
            kernel_id = await self._ensure_kernel()
            await self._initialize(kernel_id)
            return True

    async def _ensure_kernel(self):
        models = await resolved(self.manager.list_kernels())
        if self.kernel_id and any(model['id'] == self.kernel_id for model in models):
            return self.kernel_id
        existing = await resolved(self.sessions.list_sessions())
        names = {session.get('name') for session in existing}
        while True:
            self.number += 1
            name = f'JupyterExcel - {self.username} - {self.number}'
            if name not in names:
                break
        session = await resolved(self.sessions.create_session(
            path='jupyterexcel-' + uuid.uuid4().hex,
            name=name,
            type='console',
            kernel_name='python3',
        ))
        self.kernel_id = session['kernel']['id']
        return self.kernel_id

    async def _notebooks(self):
        from .office_addin import scan_notebook

        notebooks = []
        seen = set()

        async def visit(path):
            model = await resolved(self.contents.get(path, content=True))
            if model['type'] == 'directory':
                for child in sorted(model.get('content') or [], key=lambda item: item['path']):
                    if child['type'] in {'directory', 'notebook'}:
                        await visit(child['path'])
            elif model['type'] == 'notebook':
                functions = [
                    function for function in scan_notebook(model['content'], path)
                    if function.kind == 'jupyter' or function.action
                ]
                for function in functions:
                    key = function.function_id
                    if key in seen:
                        raise ExecutionError(
                            500,
                            'duplicate_function',
                            'Duplicate exported function: ' + function.function_id,
                        )
                    seen.add(key)
                if functions:
                    cells = []
                    for cell_number, cell in enumerate(model['content'].get('cells', []), 1):
                        if cell.get('cell_type') == 'code':
                            source = cell.get('source', '')
                            cells.append((
                                cell_number,
                                ''.join(source) if isinstance(source, list) else source,
                            ))
                    notebooks.append((path, cells))

        await visit('')
        return notebooks

    async def reload_notebook(self, path):
        """Serialize an explicit reload with Excel requests; never interrupt busy work."""
        try:
            await asyncio.wait_for(self.lock.acquire(), self.timeout)
        except asyncio.TimeoutError:
            raise ExecutionError(503, 'kernel_busy', 'Excel requests are still running; retry the reload.') from None
        try:
            kernel_id = await self._ensure_kernel()
            deadline = asyncio.get_running_loop().time() + self.timeout
            while True:
                models = await resolved(self.manager.list_kernels())
                model = next((m for m in models if m['id'] == kernel_id), None)
                if model is None:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise ExecutionError(503, 'kernel_busy', 'The kernel is unavailable; retry the reload.')
                    kernel_id = await self._ensure_kernel()
                    await asyncio.sleep(0.1)
                    continue
                if model.get('execution_state') != 'busy':
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    raise ExecutionError(503, 'kernel_busy', 'The kernel is still busy; retry the reload.')
                await asyncio.sleep(0.1)
            await self._initialize(kernel_id, reload_path=path)
            return kernel_id
        finally:
            self.lock.release()

    async def _initialize(self, kernel_id, reload_path=None):
        from jupyter_client import AsyncKernelClient

        kernel = self.manager.get_kernel(kernel_id)
        client = AsyncKernelClient(parent=kernel)
        client.load_connection_info(kernel.get_connection_info())
        client.start_channels()

        async def run(code):
            message_id = client.execute(code, silent=True, store_history=False, allow_stdin=False)
            while True:
                message = await client.get_shell_msg()
                if message.get('parent_header', {}).get('msg_id') == message_id:
                    if message['content'].get('status') != 'ok':
                        raise ExecutionError(
                            500,
                            'notebook_load_failed',
                            message['content'].get(
                                'evalue',
                                'Notebook initialization failed; inspect the managed kernel.',
                            ),
                        )
                    return

        try:
            await client.wait_for_ready(timeout=self.timeout)
            notebooks = await self._notebooks()
            selected = []
            if reload_path is not None:
                selected = [entry for entry in notebooks if entry[0] == reload_path]
                if not selected:
                    model = await resolved(self.contents.get(reload_path, content=True))
                    if model['type'] != 'notebook':
                        raise ExecutionError(400, 'notebook_required', 'Select a saved notebook.')
                    cells = [(i, ''.join(c.get('source', '')) if isinstance(c.get('source', ''), list)
                              else c.get('source', ''))
                             for i, c in enumerate(model['content'].get('cells', []), 1)
                             if c.get('cell_type') == 'code']
                    selected = [(reload_path, cells)]
                    notebooks.extend(selected)
            payload = json.dumps(notebooks)
            code = """if not globals().get('_jupyterexcel_initialized', False):
    if globals().get('_jupyterexcel_initializing', False):
        raise RuntimeError('Previous initialization failed; restart this kernel before retrying.')
    _jupyterexcel_initializing = True
    import json as _jupyterexcel_json
    for _jupyterexcel_path, _jupyterexcel_cells in _jupyterexcel_json.loads(%r):
        for _jupyterexcel_index, _jupyterexcel_source in _jupyterexcel_cells:
            _jupyterexcel_result = get_ipython().run_cell(_jupyterexcel_source, store_history=False)
            if not _jupyterexcel_result.success:
                raise RuntimeError('Notebook initialization failed: %%s, cell %%s' %% (_jupyterexcel_path, _jupyterexcel_index))
    _jupyterexcel_initialized = True
    _jupyterexcel_initializing = False
""" % payload
            if reload_path is not None:
                # A cold kernel initializes all exported notebooks once, including
                # the selected notebook. A warm kernel reruns only the selected one.
                code = "_jupyterexcel_was_initialized = globals().get('_jupyterexcel_initialized', False)\n" + code
                code += """
if _jupyterexcel_was_initialized:
    import json as _jupyterexcel_json
    for _jupyterexcel_path, _jupyterexcel_cells in _jupyterexcel_json.loads(%r):
        for _jupyterexcel_index, _jupyterexcel_source in _jupyterexcel_cells:
            _jupyterexcel_result = get_ipython().run_cell(_jupyterexcel_source, store_history=False)
            if not _jupyterexcel_result.success:
                raise RuntimeError('Notebook reload failed: %%s, cell %%s; earlier cells may have changed kernel state' %% (_jupyterexcel_path, _jupyterexcel_index))
""" % json.dumps(selected)
            await asyncio.wait_for(run(code), self.timeout)
        except asyncio.TimeoutError:
            raise ExecutionError(
                504,
                'timeout',
                'Notebook initialization timed out; it may still be running.',
            ) from None
        finally:
            client.stop_channels()

    async def execute(self, function_id, inputs, idle_only=False, action=None):
        async with self.lock:
            kernel_id = await self._ensure_kernel()
            models = await resolved(self.manager.list_kernels())
            model = next(model for model in models if model['id'] == kernel_id)
            if model.get('execution_state') == 'busy':
                raise ExecutionError(
                    503,
                    'kernel_busy',
                    'The JupyterExcel kernel is busy; retry when it is idle.',
                )
            await self._initialize(kernel_id)
            manager = self.manager

            class SelectedKernel:
                def list_kernels(self):
                    return [{'id': kernel_id, 'execution_state': 'idle'}]

                def get_kernel(self, selected_id):
                    return manager.get_kernel(selected_id)

            return await KernelExecutor(SelectedKernel(), self.timeout).execute(
                function_id,
                inputs,
                **({"action": action} if action is not None else {}),
            )
