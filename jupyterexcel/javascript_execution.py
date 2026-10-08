"""Dedicated, serialized Jupyter kernels for saved JavaScript notebooks."""
import asyncio
import json
import uuid
from .execution import ExecutionError, resolved
from .javascript import is_javascript
from .actions import validate_value


class JavaScriptExecutor:
    def __init__(self, manager, contents, timeout=30):
        self.manager, self.contents, self.timeout = manager, contents, timeout
        self.workers, self.locks = {}, {}
        self.closed = False

    async def catalog(self):
        from .discovery import selected_notebooks
        from .office_addin import scan_notebook
        entries = {}
        for path, model in await selected_notebooks(self.contents):
            notebook = model['content']
            if not is_javascript(notebook):
                continue
            for function in await asyncio.to_thread(scan_notebook, notebook, path):
                key = function.function_id.casefold()
                if key in entries:
                    raise ExecutionError(500, 'duplicate_function', 'Duplicate JavaScript export: ' + key)
                entries[key] = (function, notebook)
        return entries

    async def _dispose(self, path):
        worker = self.workers.pop(path, None)
        if worker:
            worker['client'].stop_channels()
            try:
                await resolved(self.manager.shutdown_kernel(worker['id'], now=True))
            except KeyError:
                pass

    async def _run(self, client, code, marker=None):
        message_id = client.execute(code, store_history=False, allow_stdin=False, silent=False)
        result = None
        async def receive():
            nonlocal result
            while True:
                message = await client.get_iopub_msg()
                if message.get('parent_header', {}).get('msg_id') != message_id:
                    continue
                kind, content = message['msg_type'], message['content']
                if kind == 'error':
                    raise ExecutionError(500, 'javascript_error', content.get('ename', 'Error') + ': ' + content.get('evalue', ''))
                if kind in ('display_data', 'execute_result') and marker:
                    data = content.get('data', {}).get('application/json', {})
                    if isinstance(data, dict) and data.get('request') == marker:
                        result = data
                if kind == 'status' and content.get('execution_state') == 'idle':
                    return result
        async def shell_reply():
            while True:
                message = await client.get_shell_msg()
                if message.get('parent_header', {}).get('msg_id') == message_id:
                    return
        tasks = [asyncio.create_task(receive()), asyncio.create_task(shell_reply())]
        try:
            values = await asyncio.wait_for(asyncio.gather(*tasks), self.timeout)
            return values[0]
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _worker(self, function, notebook):
        path = function.notebook
        worker = self.workers.get(path)
        alive = False
        if worker:
            try:
                alive = await resolved(self.manager.get_kernel(worker['id']).is_alive())
            except KeyError:
                pass
        if worker and (worker['version'] != function.version or not alive):
            await self._dispose(path)
            worker = None
        if worker:
            return worker
        kernel_name = notebook.get('metadata', {}).get('kernelspec', {}).get('name', 'deno')
        kernel_id = await resolved(self.manager.start_kernel(kernel_name=kernel_name))
        client = self.manager.get_kernel(kernel_id).client()
        client.start_channels()
        worker = dict(id=kernel_id, client=client, version=function.version)
        self.workers[path] = worker
        try:
            await client.wait_for_ready(timeout=self.timeout)
            for cell in notebook.get('cells', []):
                if cell.get('cell_type') == 'code':
                    await self._run(client, ''.join(cell.get('source', '')))
        except BaseException:
            await self._dispose(path)
            raise
        return worker

    async def execute(self, function_id, inputs, action=None, version=None, entry=None):
        if self.closed:
            raise ExecutionError(503, 'kernel_closed', 'JavaScript execution is shutting down.')
        entry = entry or (await self.catalog()).get(function_id.casefold())
        if entry is None:
            return None
        function, notebook = entry
        if function.execution != 'server':
            raise ExecutionError(400, 'local_function', 'This function runs in the Excel add-in.')
        if action is False and function.kind == 'ribbon':
            raise ExecutionError(405, 'action_requires_post', 'Ribbon actions require POST.')
        if version and version != function.version:
            raise ExecutionError(409, 'stale_export', 'Notebook changed. Reload the add-in before calling this function.')
        if len(inputs) > len(function.parameters):
            raise ExecutionError(400, 'invalid_arguments', 'Too many arguments.')
        try:
            for i, parameter in enumerate(function.parameters):
                if i >= len(inputs) and parameter.optional:
                    continue
                if i >= len(inputs):
                    raise ValueError('Missing argument: ' + parameter.name)
                value = inputs[i]
                validate_value(value, 'matrix' if parameter.dimensionality == 'matrix' else parameter.type)
                if parameter.dimensionality == 'matrix':
                    for row in value:
                        for cell in row:
                            validate_value(cell, parameter.type)
        except ValueError as error:
            raise ExecutionError(400, 'invalid_arguments', str(error)) from error
        lock = self.locks.setdefault(function.notebook, asyncio.Lock())
        async def invoke():
            async with lock:
                worker = await self._worker(function, notebook)
                marker = uuid.uuid4().hex
                # Only parser-validated identifiers and JSON arguments enter code.
                code = ('await Deno.jupyter.display({"application/json": {request: ' + json.dumps(marker) +
                        ', result: await ' + function.python_name + '(...' + json.dumps(inputs) + ')}}, {raw: true});')
                try:
                    envelope = await self._run(worker['client'], code, marker)
                    if not envelope or 'result' not in envelope:
                        raise ExecutionError(500, 'invalid_result', 'JavaScript returned no serializable result.')
                    result = envelope['result']
                    validate_value(result, 'matrix' if function.result_dimensionality == 'matrix' else function.result_type)
                    if function.result_dimensionality == 'matrix':
                        for row in result:
                            for cell in row:
                                validate_value(cell, function.result_type)
                    return {'ok': True, 'result': result}
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    await self._dispose(function.notebook)
                    raise
                except ValueError as error:
                    raise ExecutionError(500, 'invalid_result', str(error)) from error
        try:
            return await asyncio.wait_for(invoke(), self.timeout)
        except asyncio.TimeoutError:
            raise ExecutionError(504, 'timeout', 'JavaScript execution timed out; no automatic retry was performed.') from None

    async def reload_notebook(self, path):
        async with self.locks.setdefault(path, asyncio.Lock()):
            await self._dispose(path)
        return None

    async def stop(self):
        self.closed = True
        for path in list(self.workers):
            async with self.locks.setdefault(path, asyncio.Lock()):
                await self._dispose(path)
