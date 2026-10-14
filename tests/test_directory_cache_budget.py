"""Memory budgets for browsing large and changing G-code directory trees."""
import unittest
from unittest.mock import Mock

from test_capabilities import printer, snapshot
from test_regressions import backend
MoonrakerError = backend.MoonrakerError


class DirectoryCacheBudgetTests(unittest.TestCase):
    def make(self):
        backend = printer(snapshot())
        backend.client.get = Mock(return_value={'result': {'value': {}}})
        backend.getREST = Mock(side_effect=lambda path: (
            {'result': []} if path == '/server/files/list'
            else {'result': {'dirs': [], 'files': []}}))
        return backend

    def test_many_directories_have_bounded_cache_and_preserve_root(self):
        backend = self.make()
        backend.GetDirectory('')
        for index in range(130):
            backend.GetDirectory('folder{}'.format(index))
        self.assertLessEqual(len(backend._directory_cache), 64)
        self.assertIn((backend.state.epoch, backend.state.file_revision, ''),
                      backend._directory_cache)
        self.assertIn((backend.state.epoch, backend.state.file_revision, 'folder129'),
                      backend._directory_cache)
        self.assertNotIn((backend.state.epoch, backend.state.file_revision, 'folder0'),
                         backend._directory_cache)

    def test_retry_deadlines_are_bounded_and_reset_on_revision(self):
        backend = self.make()
        def fail_directory(path):
            if path == '/server/files/list':
                return {'result': []}
            raise MoonrakerError('read failure')
        backend.getREST.side_effect = fail_directory
        for index in range(110):
            backend.GetDirectory('missing{}'.format(index))
        self.assertLessEqual(len(backend._directory_retry_at), 64)
        new = snapshot()
        new['file_revision'] = backend.state.file_revision + 1
        backend.subscription.snapshot.return_value = new
        backend.update_variable()
        backend.GetDirectory('new_missing')
        self.assertEqual(list(backend._directory_retry_at),
                         [(new['epoch'], new['file_revision'], 'new_missing')])
