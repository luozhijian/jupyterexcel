"""Per-server kernel selection and JSON worksheet execution."""
import asyncio
import ast
import inspect
import json


class ExecutionError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


async def resolved(value):
    return await value if inspect.isawaitable(value) else value


def invoke_export(function_id, inputs):
    """Runs inside the kernel; never evaluate a caller-supplied expression."""
    from IPython import get_ipython
    namespace = get_ipython().user_ns
    matches = {}
    for value in list(namespace.values()):
        metadata = getattr(value, '__jupyterexcel_function__', None)
        if callable(value) and isinstance(metadata, dict):
            name = metadata.get('id', '')
            normalized = ''.join(c if c.isascii() and (c.isalnum() or c == '.') else '.' for c in name).upper().strip('.')
            if normalized == function_id.upper():
                matches[id(value)] = value
    if len(matches) != 1:
        return json.dumps({'ok': False, 'error': {'code': 'function_not_found' if not matches else 'duplicate_function', 'message': 'Expected one exported function in the selected kernel.'}})
    function = next(iter(matches.values()))
    try:
        inspect.signature(function).bind(*inputs)
    except TypeError as error:
        return json.dumps({'ok': False, 'error': {'code': 'invalid_arguments', 'message': str(error)}})
    try:
        result = function(*inputs)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TypeError('Async worksheet functions are not supported in this version.')
        return json.dumps({'ok': True, 'result': result}, allow_nan=False)
    except Exception as error:
        return json.dumps({'ok': False, 'error': {'code': 'execution_failed', 'message': str(error)}})


class KernelExecutor:
    def __init__(self, manager, timeout=30):
        self.manager, self.timeout = manager, timeout
        self.reserved = set()
        self.lock = asyncio.Lock()

    async def execute(self, function_id, inputs, idle_only=False):
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
