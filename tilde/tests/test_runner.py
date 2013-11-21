from twisted.trial import unittest
from twisted.internet import task, defer
from twisted.python import log
from twisted.application import service

from tilde.runner import UpdaterService

import logging
class THandler(logging.Handler):
    def emit(self, record):
        fmt = self.format(record)
        log.msg(fmt)

hdlr = THandler()
fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s', None)
hdlr.setFormatter(fmt)
logging.root.addHandler(hdlr)
logging.root.setLevel(logging.DEBUG)

class MockUpdater(object):
    def __init__(self):
        self.tasks = {}

    def listSharesToUpdate(self, since=None):
        log.msg("Returning {0} tasks to process".format(len(self.tasks)))
        return list(self.tasks)

    def updateOne(self, home, status):
        log.msg("Processing home {0!r} {1!r}".format(home, status))
        d = self.tasks.pop((home, status))
        return d

class UpdaterServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.clock = task.Clock()

        self.root = root = service.MultiService()
        self.mock = mock = MockUpdater()
        root.updater = mock

        self.us = UpdaterService(interval=30, clock=self.clock)
        root.addService(self.us)
        self.us.parent = root
        root.startService()

    def tearDown(self):
        self.root.stopService()

    def _advance(self, time=35, increment=1):
        while time > 0:
            self.clock.advance(min(increment, time))
            time -= increment

    def test_simple(self):
        self._advance()
        self.assertFalse(self.mock.tasks, "tasks should be empty")

        d = defer.succeed("yay")
        self.mock.tasks[("h1", "s1")] = d
        self._advance()
        self.assertFalse(self.mock.tasks, "tasks should be empty")

    def test_failing_work(self):
        self._advance()
        d = defer.fail("oh noes")
        self.mock.tasks[("h1", "s1")] = d
        self._advance()
        self.assertFalse(self.mock.tasks, "tasks should be empty")

        self._advance()
        d = defer.fail("oh noes again")
        self.mock.tasks[("h2", "s2")] = d
        self._advance()
        self.assertFalse(self.mock.tasks, "tasks should be empty")

    def test_unfinished_business(self):
        self._advance()
        d = defer.Deferred()
        self.mock.tasks[("h1", "s1")] = d
        self._advance()
        self.assertFalse(self.mock.tasks, "tasks should be empty")

        d2 = defer.Deferred()
        self.mock.tasks[("h2", "s2")] = d2
        self._advance()
        self.assertFalse(self.mock.tasks, "tasks should be empty")

    test_unfinished_business.skip = "Normal behavior not defined yet"
