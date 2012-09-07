import os

from twisted.python import log
from twisted.internet import defer
from zope.interface import implements
from storm.zope.zstorm import IZStorm

from tilde import core, models


class MockZStorm(object):
    implements(IZStorm)

    def __init__(self, db):
        self.db = db

    def get(self, name):
        return self.db


class MockStore(object):
    def __init__(self):
        self.objects = {
            models.Home : {},
            models.HomeState : {},
            }
        self._ids = iter(xrange(10**10))

    def _dbkeys(self, obj):
        cls = type(obj)
        try:
            keys = cls.__storm_primary__
        except AttributeError:
            keys = [c.name
                    for c in cls._storm_columns.itervalues()
                    if c.primary]
        return cls, keys

    def get(self, cls, key):
        res = self.objects.get(cls, {}).get(key)
        log.msg("DB get {0}: {1}".format(cls, key, res))
        return res

    def find(self, cls, *cond):
        def _m(obj):
            for c in cond:
                if c.oper != " = ":
                    raise Exception("Can't test this")
                vals = []
                for v in (c.expr1, c.expr2):
                    try:
                        vals.append(getattr(obj, v.name))
                    except AttributeError:
                        vals.append(v.get())
                if vals[0] != vals[1]: return False

            return True

        res = [val
               for val in self.objects.get(cls, {}).itervalues()
               if _m(val)]
        log.msg("DB find {0} : {1} -> {2}".format(cls, cond, res))
        return res

    def add(self, obj):
        log.msg("DB add: {0}".format(obj))
        cls, keys = self._dbkeys(obj)

        for k in keys:
            if getattr(obj, k) is None:
                setattr(obj, k, next(self._ids))

        key = tuple(getattr(obj, k) for k in keys)
        self.objects.setdefault(cls, {})[key] = obj

    def remove(self, obj):
        log.msg("DB remove: {0}".format(obj))
        cls, keys = self._dbkeys(obj)

        key = tuple(getattr(obj, k) for k in keys)
        self.objects.get(cls, {}).pop(key)


class MockServerManager(core.ServerManager):
    def _makeUpdater(self, server, config):
        return MockShareUpdater(server, config)

    def _openConnection(self, name, config):
        return defer.succeed(MockSSHServer())

class MockSSHServer(object):
    def loseConnection(self):
        ''' Fake disconnect '''


class MockShareUpdater(core.ShareUpdater):
    def __init__(self, *a):
        core.ShareUpdater.__init__(self, *a)
        self.known_paths = set("/")


    def _make_parent(self, path):
        head, tail = os.path.split(os.path.normpath(path))
        while head and head not in self.known_paths:
            self.known_paths.add(head)
            head, tail = os.path.split(head)

        return defer.succeed(True)

    def exists(self, path):
        return defer.succeed(path in self.known_paths)

    def get_path_info(self, path):
        if path in self.known_hosts:
            res = {"type":"directory",
                   "user":"user",
                   "group":"group",
                   "mode":0o700}
        else:
            res = None

        return defer.succeed(res)

    def create_home(self, home):
        path = self.get_real_path(home.path)
        self.known_paths.add(path)
        return defer.succeed(True)

    def sync(self, fromState, to, home, bwlimit=None):
        assert isinstance(to, MockShareUpdater), "Don't want to accidently"

        if fromState.status == models.HomeState.ACTIVE:
            src_base = self.root
        else:
            src_base = self.archive_root

        sourcepath = self.get_real_path(fromState.path, src_base)
        to_path = to.get_real_path(home.path)

        d = to._make_parent(to_path)
        def _then(*r):
            to.known_paths.add(to_path)

        d.addBoth(_then)
        return d


    def _move(self, source, dest):
        log.msg("[{0.name}] MV {1!r} -> {2!r}".format(self, source, dest))
        self.known_paths.remove(source)
        self.known_paths.add(dest)
        return defer.succeed(True)
