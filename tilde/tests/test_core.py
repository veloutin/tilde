from __future__ import unicode_literals

from twisted.trial import unittest
from twisted.internet import reactor, defer
from twisted.python.threadpool import ThreadPool
from storm.twisted.transact import Transactor

from zope.component import getGlobalSiteManager
GSM = getGlobalSiteManager()

from .mock import (
    MockStore,
    MockZStorm,
    MockServerManager,
)

from tilde.models import Home, HomeState
from tilde.loader import Server
from tilde.runner import Updater

SERVERS = {
    "foo" : Server("foo", "/data/homes", archive_root="/data/archive"),
    "bar" : Server("bar", "/data/homes", archive_root="/data/archive"),
}

class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.db = MockStore()
        GSM.registerUtility(MockZStorm(self.db))

        self.tp = ThreadPool(0, 2)
        self.sm = MockServerManager(reactor, SERVERS)
        self.updater = Updater(Transactor(self.tp), self.sm)
        self.tp.start()

    def tearDown(self):
        self.tp.stop()

    def _H(self, **k):
        h = Home()
        for k, v in k.iteritems():
            setattr(h, k, v)
        self.db.add(h)
        return h

    def _S(self, **k):
        h = HomeState()
        for k, v in k.iteritems():
            setattr(h, k, v)
        self.db.add(h)
        return h

    @defer.inlineCallbacks
    def test_creation(self):
        home = self._H(
            server_name = "foo",
            path = "/test",
        )

        fooserv = yield self.sm.getServer("foo")

        self.assertNotIn((home.id, "foo"), self.db.objects[HomeState])
        self.assertNotIn("/data/homes/test", fooserv.known_paths)

        done = yield self.updater.updateOne(home, [])

        self.assertIn((home.id, "foo"), self.db.objects[HomeState])
        self.assertIn("/data/homes/test", self.sm.servers["foo"].known_paths)

    @defer.inlineCallbacks
    def test_move(self):
        home = self._H(
            server_name = "foo",
            path = "/test",
        )

        status = self._S(
            id = home.id,
            server_name = "foo",
            path = "/old_dir",
            status = HomeState.ACTIVE,
        )

        fooserv = yield self.sm.getServer("foo")
        fooserv.known_paths.add("/data/homes/old_dir")

        done = yield self.updater.updateOne(home, [status])

        self.assertIn((home.id, "foo"), self.db.objects[HomeState])
        status = self.db.objects[HomeState][(home.id, "foo")]
        self.assertEquals(status.path, home.path)

        self.assertIn("/data/homes/test", self.sm.servers["foo"].known_paths)
        self.assertNotIn("/data/homes/old_dir", self.sm.servers["foo"].known_paths)


    @defer.inlineCallbacks
    def test_archive(self):
        home = self._H(
            server_name = "foo",
            path = None,
        )

        status = self._S(
            id = home.id,
            server_name = "foo",
            path = "/foo",
            status = HomeState.ACTIVE,
        )

        fooserv = yield self.sm.getServer("foo")
        fooserv.known_paths.add("/data/homes/foo")

        self.assertNotIn("/data/archive/foo", fooserv.known_paths)

        done = yield self.updater.updateOne(home, [status])

        status = self.db.objects[HomeState][(home.id, "foo")]
        self.assertEquals(status.status, HomeState.ARCHIVED)

        self.assertIn("/data/archive/foo", fooserv.known_paths)
        self.assertNotIn("/data/homes/foo", fooserv.known_paths)

    @defer.inlineCallbacks
    def test_sync(self):
        home = self._H(
            server_name = "foo",
            path="/foo",
        )

        status = self._S(
            id=home.id,
            server_name="bar",
            path="/bar",
            status=HomeState.ACTIVE,
        )

        fooserv = yield self.sm.getServer("foo")
        barserv = yield self.sm.getServer("bar")

        barserv.known_paths.add("/data/homes/bar")
        self.assertNotIn("/data/homes/foo", fooserv.known_paths)

        done = yield self.updater.updateOne(home, [status])

        status = self.db.objects[HomeState][(home.id, "foo")]
        self.assertEquals(status.server_name, "foo")
        self.assertEquals(status.path, "/foo")
        self.assertEquals(status.status, HomeState.ACTIVE)


        self.assertNotIn((home.id, "bar"), self.db.objects[HomeState])
        self.assertIn("/data/homes/foo", fooserv.known_paths)
        self.assertNotIn("/data/homes/bar", barserv.known_paths)


    @defer.inlineCallbacks
    def test_load_remote_archive(self):
        home = self._H(
            server_name="foo",
            path="/foo",
        )

        status = self._S(
            id=home.id,
            server_name="bar",
            path="/baz",
            status=HomeState.ARCHIVED,
        )

        fooserv = yield self.sm.getServer("foo")
        barserv = yield self.sm.getServer("bar")

        barserv.known_paths.add("/data/archive/baz")
        self.assertNotIn("/data/homes/foo", fooserv.known_paths)

        done = yield self.updater.updateOne(home, [status])

        self.assertIn("/data/homes/foo", fooserv.known_paths)
        self.assertNotIn("/data/homes/baz", barserv.known_paths)

        self.assertNotIn((home.id, "bar"), self.db.objects[HomeState])

        newstate = self.db.objects[HomeState][(home.id, "foo")]
        self.assertEquals(newstate.path, "/foo")
        self.assertEquals(newstate.status, HomeState.ACTIVE)
        self.assertEquals(newstate.server_name, "foo")


    @defer.inlineCallbacks
    def test_load_local_archive(self):
        home = self._H(
            server_name="bar",
            path="/foo",
        )

        status = self._S(
            id=home.id,
            server_name="bar",
            path="/baz",
            status=HomeState.ARCHIVED,
        )

        barserv = yield self.sm.getServer("bar")
        barserv.known_paths.add("/data/archive/baz")
        self.assertNotIn("/data/homes/foo", barserv.known_paths)

        done = yield self.updater.updateOne(home, [status])

        self.assertIn("/data/homes/foo", barserv.known_paths)
        self.assertNotIn("/data/homes/baz", barserv.known_paths)

        newstate = self.db.objects[HomeState][(home.id, "bar")]
        self.assertEquals(newstate.path, "/foo")
        self.assertEquals(newstate.status, HomeState.ACTIVE)
        self.assertEquals(newstate.server_name, "bar")


    @defer.inlineCallbacks
    def test_clean_others(self):
        home = self._H(
            server_name="bar",
            path="/bar",
        )

        s1 = self._S(
            id=home.id,
            server_name="bar",
            path="/bar",
            status=HomeState.ACTIVE,
        )

        s2 = self._S(
            id=home.id,
            server_name="foo",
            path="/bar",
            status=HomeState.ACTIVE,
        )

        fooserv = yield self.sm.getServer("foo")
        barserv = yield self.sm.getServer("bar")

        fooserv.known_paths.add("/data/homes/bar")
        barserv.known_paths.add("/data/homes/bar")

        done = yield self.updater.updateOne(home, [s1, s2])

        self.assertIn("/data/homes/bar", barserv.known_paths)
        self.assertNotIn("/data/homes/bar", fooserv.known_paths)

        self.assertIn((home.id, "bar"), self.db.objects[HomeState])
        self.assertNotIn((home.id, "foo"), self.db.objects[HomeState])

