from __future__ import unicode_literals

import logging
mlog = logging.getLogger(__name__)

import itertools
import operator

from zope.component import getUtility

from storm.zope.zstorm import IZStorm
from storm.twisted.transact import Transactor, transact
from storm.expr import LeftJoin, Desc

from twisted.internet import defer
from twisted.python.threadpool import ThreadPool



from tilde.models import Home, HomeState
from tilde.core import ShareUpdater

from tilde.core import ServerManager

def run(dburl, server, share_root, archive_root):
    mlog.debug("Connecting to {0}".format(dburl))
    store = Store(create_database(dburl))

    mlog.debug("Setting up updater: {0}"
               .format(", ".join([
                   server,
                   share_root,
                   archive_root or "<none>"
               ])))
    updater = ShareUpdater(server, share_root, archive_root)

    requested = store.using(
        Home,
        LeftJoin(
            HomeState,
            Home.id == HomeState.id,
        )
    ).find((Home, HomeState), Home.server_name == server)

    inactive = store.find(
        (Home, HomeState),
        Home.id == HomeState.id,
        Home.server_name != server,
        HomeState.server_name == server,
    )

    mlog.info("Found {0} shares to update".format(requested.count()))

    for home, state in requested:
        mlog.debug("Updating {0} ({1})".format(home, state))
        if state is None:
            state = HomeState()
            state.home = home

        try:
            updater.update(home, state)
            mlog.debug("- State is now {0}".format(state))
        except Exception:
            mlog.exception("Failed to update home: {0}".format(home))
            store.reload(home)
            if Store.of(state) is store:
                store.reload(state)
            store.rollback()
            continue

        try:
            if Store.of(state) is None:
                store.add(state)
            store.commit()
        except Exception:
            store.rollback()
            mlog.exception("Failed to commit changes")

    mlog.info("Found {0} shares to remove".format(inactive.count()))
    for home, state in inactive:
        mlog.debug("Deactivating {0} ({1})".format(home, state))
        try:
            updater.update(home, state)
            mlog.debug("- State is now {0}".format(state))
        except Exception:
            store.reload(home)
            store.reload(state)
            mlog.exception("Failed to update home: {0}".format(home))
            store.rollback()
            continue

        try:
            #Inactive should mean old state gets flushed
            if state.path is None:
                store.remove(state)
            store.commit()
        except Exception:
            store.rollback()
            mlog.exception("Failed to commit changes")


class Updater(object):
    def __init__(self, transactor, serverManager):
        self.transactor = transactor
        self.serverManager = serverManager

    @transact
    def listSharesToUpdate(self, since=None):
        zs = getUtility(IZStorm).get("tilde")
        for home, status in itertools.groupby(
                zs.using(
                        Home,
                        LeftJoin(
                            HomeState,
                            Home.id == HomeState.id,
                        ))
                    .find((Home, HomeState))
                    .order_by(Home.id, Desc(HomeState.ts)),
                operator.itemgetter(0)):

            status = [s for h,s in status if s is not None]
            if ((len(status) > 1) or
                (home.active and not status) or
                (status and not home.match(status[0]))):
                yield home, status

    @transact
    def deleteState(self, homestate):
        zs = getUtility(IZStorm).get("tilde")
        # Get a local copy for thread safety reasons
        hs = zs.get(HomeState, (homestate.id, homestate.server_name))
        zs.remove(hs)

    @transact
    def updateState(self, homestate):
        zs = getUtility(IZStorm).get("tilde")
        # Get a local copy for thread safety reasons
        hs = zs.get(HomeState, (homestate.id, homestate.server_name))
        if hs:
            hs.update(homestate)
        else:
            zs.add(HomeState.fromState(homestate))

    def create(self, home):
        print "creating home", home
        self.updateState(HomeState.fromHome(home,
                                            server=home.server_name,
                                            path=home.path))
        return defer.succeed(True)

    def migrate(self, home, fromState):
        print "migrating", home, fromState, home.server_name
        self.updateState(HomeState.fromHome(home,
                                            server=home.server_name,
                                            path=home.path))
        self.deleteState(fromState)
        return defer.succeed(True)

    def archive(self, homestate):
        print "Archiving", homestate
        homestate.status = HomeState.ARCHIVED
        self.updateState(homestate)
        return defer.succeed(True)

    def remove(self, homestate):
        print "Clearing up the homestate", homestate
        self.deleteState(homestate)
        return defer.succeed(True)

    def updateOne(self, home, status):
        res = defer.Deferred()
        source = next(
            itertools.chain(
                (s for s in status if s.status == HomeState.ACTIVE),
                (s for s in status if s.status == HomeState.ARCHIVED),
            ),
            None)
        if home.active:
            if source:
                ops = [self.remove(s) for s in status if s is not source]
                cleanup = defer.DeferredList(ops)
                def _cleanupDone(*i):
                    if not home.match(source):
                        self.migrate(home, source).chainDeferred(res)
                    else:
                        defer.succeed("Nothing else to do").chainDeferred(res)
                cleanup.addCallbacks(_cleanupDone, res.errback)
            else:
                self.create(home).chainDeferred(res)

        else:
            if source:
                ops = [self.remove(s) for s in status if s is not source]
                cleanup = defer.DeferredList(ops)
                def _done(*i):
                    self.archive(source).chainDeferred(res)
                cleanup.addCallbacks(_done, res.errback)
            else:
                defer.succeed("Nothing to do").chainDeferred(res)

        return res

if __name__ == '__main__':
    from twisted.internet import reactor
    from tilde.loader import load_config, setup_environment
    from twisted.python.log import startLogging
    import sys
    startLogging(sys.stdout)
    cfg = load_config("etc/tilde.ini")
    setup_environment(cfg)
    tp = ThreadPool(0, 5)

    def _s():
        tp.start()
        tx = Updater(Transactor(tp), None)
        servers = tx.listSharesToUpdate()
        def p(res):
            updates = [tx.updateOne(*r) for r in res]
            dl = defer.DeferredList(updates)
            def _done(*r):
                tp.stop()
                reactor.stop()
            dl.addBoth(_done)

        servers.addCallback(p)

    reactor.callWhenRunning(_s)
    trigId = reactor.addSystemEventTrigger("before", "shutdown", tp.stop)
    reactor.run()
    
