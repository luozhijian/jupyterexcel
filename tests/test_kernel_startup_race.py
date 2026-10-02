import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from traitlets import TraitError
from tornado.web import HTTPError
from jupyter_server.services.kernels.kernelmanager import ServerKernelManager
from jupyterexcel.execution import kernel_states, KernelExecutor, ExecutionError


class StartupRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uninitialized_activity_does_not_break_ready_kernel_listing(self):
        starting = ServerKernelManager()
        with self.assertRaises(TraitError):
            _ = starting.last_activity
        ready = SimpleNamespace(execution_state='idle')
        kernels = {'starting': starting, 'ready': ready}
        manager = SimpleNamespace(list_kernel_ids=lambda: list(kernels),
            get_kernel=kernels.__getitem__, list_kernels=Mock(side_effect=AssertionError('must not serialize timestamps')))
        models = await kernel_states(manager)
        self.assertEqual(models, [{'id': 'starting', 'execution_state': 'starting'},
                                  {'id': 'ready', 'execution_state': 'idle'}])
        manager.list_kernels.assert_not_called()
        self.assertNotIn('last_activity', starting._trait_values)
        starting.execution_state = 'idle'
        self.assertEqual((await kernel_states(manager))[0]['execution_state'], 'idle')

    async def test_removed_kernel_is_skipped_but_other_errors_are_not_hidden(self):
        for error in (KeyError('gone'), HTTPError(404)):
            manager = SimpleNamespace(list_kernel_ids=lambda: ['gone', 'ready'],
                get_kernel=Mock(side_effect=[error, SimpleNamespace(execution_state='idle')]))
            self.assertEqual(await kernel_states(manager), [{'id': 'ready', 'execution_state': 'idle'}])
        manager.get_kernel = Mock(side_effect=HTTPError(403))
        with self.assertRaises(HTTPError):
            await kernel_states(manager)

    async def test_starting_kernel_cannot_receive_requests(self):
        manager = SimpleNamespace(list_kernel_ids=lambda: ['starting'],
            get_kernel=lambda _: SimpleNamespace(execution_state=None))
        with self.assertRaises(ExecutionError) as error:
            await KernelExecutor(manager).execute('Sum', [])
        self.assertEqual(error.exception.code, 'no_kernel')
