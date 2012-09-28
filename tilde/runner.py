# -*- coding: utf-8 -*-
#
# (C) Copyright Révolution Linux 2012
#
# Authors:
# Vincent Vinet <vince.vinet@gmail.com>
#
# This file is part of tilde.
#
# tilde is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# tilde is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with tilde.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import itertools
import operator

from zope.component import getUtility

from storm.zope.zstorm import IZStorm
from storm.twisted.transact import Transactor, transact
from storm.expr import LeftJoin, Desc

from twisted.internet import defer
from twisted.internet import task
from twisted.python.threadpool import ThreadPool
from twisted.python.failure import Failure
from twisted.python import log

from tilde.models import Home, HomeState
from tilde.core import ServerManager



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

            status = [s.copy() for h,s in status if s is not None]
            if ((len(status) > 1) or
                (home.active and not status) or
                (status and not home.match(status[0]))):
                yield home.copy(), status

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

    @transact
    def refreshState(self, homestate):
        zs = getUtility(IZStorm).get("tilde")
        hs = zs.get(HomeState, (homestate.id, homestate.server_name))
        return hs.copy()

    @transact
    def findState(self, *condition):
        zs = getUtility(IZStorm).get("tilde")
        res = zs.find(HomeState, *condition)
        return [s.copy() for s in res]

    def create(self, home):
        res = defer.Deferred()
        log.msg("creating home {0}".format(home))
        def _success(res):
            if res:
                return self.updateState(HomeState.fromHome(home))
            else:
                return Failure(Exception("Failed to create home"))

        server = self.serverManager.getServer(home.server_name)
        server.addCallback(lambda updater: updater.create_home(home))
        server.addCallback(_success)
        server.chainDeferred(res)
        return res

    def migrate(self, home, fromState):
        res = defer.Deferred()
        src = self.serverManager.getServer(fromState.server_name)

        if home.server_name == fromState.server_name:
            log.msg("moving {0} locally".format(home))
            src.addCallback(self._move_local, home, fromState)
            return src

        log.msg("migrating {0} from {1}".format(home, fromState))

        def _done(res):
            d1 = self.updateState(HomeState.fromHome(home))
            d1.addCallback(lambda res: self.refreshState(fromState))
            d1.addCallback(lambda newState: self.remove(newState))
            return d1


        dst = self.serverManager.getServer(home.server_name)
        dl = defer.DeferredList([src, dst], fireOnOneErrback=True)
        dl.addCallback(self._migration_start, home, fromState)
        dl.addCallback(_done)
        dl.chainDeferred(res)
        return res

    def _move_local(self, server, home, fromState):
        def _done(res):
            return self.updateState(HomeState.fromHome(home))
        res = server.move(fromState, home.path)
        res.addCallback(_done)
        return res

    def _migration_start(self, reslist, home, fromState):
        (res1, source), (res2, dest) = reslist
        if not res1 or not res2:
            return Failure(Exception("Unable to get both servers"))


        sync1 = source.sync(fromState=fromState, to=dest, home=home)
        if fromState.status == HomeState.ACTIVE:
            # Active homes need to be archived then re-synced
            sync1.addCallback(lambda res: self.archive(fromState))
            sync1.addCallback(lambda res: self.refreshState(fromState))
            def _resync(newstate):
                if newstate:
                    return source.sync(fromState=newstate,
                                       to=dest,
                                       home=home)
            sync1.addCallback(_resync)

        return sync1

    @defer.inlineCallbacks
    def _find_free_path(self, server, path, status):
        newpath = path
        suffix = 0
        while suffix < 10:
            existing = yield self.findState(
                HomeState.status == status,
                HomeState.path == newpath,
                HomeState.server_name == server)

            if not existing:
                defer.returnValue(newpath)  # This breaks and returns

            suffix += 1
            newpath = path + u"-{0}".format(suffix)
        else:
            raise Exception("Unable to find free archive path")


    def archive(self, homestate):
        log.msg("Archiving {0}".format(homestate))
        d = self.serverManager.getServer(homestate.server_name)
        get_path = self._find_free_path(homestate.server_name,
                                        homestate.path,
                                        HomeState.ARCHIVED)

        res = defer.gatherResults([get_path, d])
        def _done((newpath, server)):
            ark = server.archive(homestate, newpath)
            ark.addCallback(
                lambda res: self.updateState(
                    HomeState.fromState(homestate,
                                        status=HomeState.ARCHIVED,
                                        path=newpath)))
            return ark

        res.addCallback(_done)
        return res

    def remove(self, homestate):
        log.msg("Clearing up the homestate {0}".format(homestate))
        res = self.serverManager.getServer(homestate.server_name)
        res.addCallback(lambda server: server.remove(homestate))
        res.addCallback(lambda res: self.deleteState(homestate))
        return res


    def _update(self, res, home, source=None):
        log.msg("Updating {0} with {1}".format(home, source))
        if home.active:
            if source:
                return self.migrate(home, source)
            else:
                return self.create(home)
        else:
            if source and source.status == HomeState.ACTIVE:
                return self.archive(source)
            else:
                return defer.succeed("Nothing to do, already archived")

    def updateOne(self, home, status):
        source = next(
            itertools.chain(
                (s for s in status if s.status == HomeState.ACTIVE),
                (s for s in status if s.status == HomeState.ARCHIVED),
            ),
            None)

        clean = defer.succeed("No cleanup required")
        if source:
            to_clean = [s for s in status if s is not source]
            if to_clean:
                log.msg("Multiple statuses found, cleaning them: {0}"
                        .format(to_clean))
                ops = [self.remove(s) for s in to_clean]
                clean = defer.DeferredList(ops)

        clean.addCallback(self._update, home, source)
        return clean

def run(config, reactor=None):
    if reactor is None:
        from twisted.internet import reactor

    tp = ThreadPool(0, 5)
    tp.start()
    sm = ServerManager(reactor, config["servers"])
    trigId = reactor.addSystemEventTrigger("before", "shutdown", tp.stop)
    tx = Updater(Transactor(tp), sm)

    servers = tx.listSharesToUpdate()
    def p(res):
        work = (tx.updateOne(*r) for r in res)
        numworkers = int(config.get("workers", 10)) or 1
        workers = [task.cooperate(work).whenDone()
                   for i in xrange(numworkers)]

        dl = defer.DeferredList(workers)
        return dl
    servers.addCallback(p)

    def _done(res):
        log.msg('Done updating')
        sm.loseConnections()
        tp.stop()
        return res
    servers.addBoth(_done)

    return servers
