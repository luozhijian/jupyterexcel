"""A reusable shell-only client owned by one exclusively reserved worker."""
import asyncio


class KernelConnection:
    def __init__(self):
        self.client = None
        self.identity = None
        self.ready = False

    def open(self, kernel):
        info = kernel.get_connection_info()
        identity = (id(kernel), getattr(getattr(kernel, 'provisioner', None), 'pid', None), info)
        if self.client is not None and identity == self.identity:
            return self.client
        self.close()
        from jupyter_client import AsyncKernelClient
        client = AsyncKernelClient()
        self.client = client
        try:
            client.load_connection_info(info)
            # No heartbeat thread, stdin, control, or unconsumed IOPub socket.
            client.start_channels(shell=True, iopub=False, stdin=False, hb=False, control=False)
            self.identity = identity
            return client
        except BaseException:
            self.close()
            raise

    async def wait_for_ready(self, timeout):
        if self.ready:
            return
        # KernelClient.wait_for_ready also opens IOPub/heartbeat channels. Use
        # the kernel-info shell handshake instead; the manager monitors liveness.
        async def handshake():
            message_id = self.client.kernel_info()
            while True:
                message = await self.client.get_shell_msg()
                if (message.get('parent_header', {}).get('msg_id') == message_id
                        and message.get('header', {}).get('msg_type') == 'kernel_info_reply'):
                    self.ready = True
                    return
        await asyncio.wait_for(handshake(), timeout)

    def close(self):
        client, self.client = self.client, None
        self.identity, self.ready = None, False
        if client is not None:
            # stop_channels() accesses lazy properties even for disabled channels.
            # Close only our existing socket, including a partially started one.
            channel = getattr(client, '_shell_channel', None)
            if channel is not None:
                channel.close()
