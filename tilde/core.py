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

import os

import logging
log = logging.getLogger(__name__)

from tilde.util import log_err

from twisted.internet import defer
from twisted.internet.error import ProcessTerminated

from tilde import models
from tilde.ssh import SSHServer, RunCommandProtocol


class ServerManager(object):
    def __init__(self, reactor, servers):
        self.reactor = reactor
        self.config = servers
        self.servers = {}
        self._deferreds = {}

    def getServer(self, name):
        try:
            config = self.config[name]
        except KeyError:
            return defer.fail()

        if name in self.servers:
            return defer.succeed(self.servers[name])

        d = defer.Deferred()
        if name in self._deferreds:
            self._deferreds[name].append(d)
            return d

        self._deferreds[name] = [d]
        self._openConnection(name, config).addCallbacks(
            self._openCb,
            self._openErr,
            callbackArgs=(name, config),
            errbackArgs=(name, ),
        )
        return d

    def _makeUpdater(self, server, config):
        return ShareUpdater(server, config)

    def _openCb(self, server, name, config):
        su = self._makeUpdater(server, config)

        self.servers[name] = su
        for d in self._deferreds.pop(name, []):
            d.callback(su)

    def _openErr(self, reason, name):
            for d in self._deferreds.pop(name, []):
                d.errback(reason)

    def _openConnection(self, name, config):
        return SSHServer(self.reactor,
                      hostname=config.hostname,
                      port=config.port,
                      user=config.user).connect()

    def loseConnections(self):
        while self.servers:
            key, su = self.servers.popitem()
            for d in self._deferreds.pop(key, []):
                d.cancel()
            su.server.connection.loseConnection()


class ShareUpdater(object):
    CMD_STAT = "/usr/bin/stat"
    CMD_TEST = "/usr/bin/test"
    CMD_MKDIR = "/bin/mkdir"
    CMD_CHOWN = "/bin/chown"
    CMD_CHMOD = "/bin/chmod"
    CMD_RSYNC = "/usr/bin/rsync"
    CMD_MOVE = "/bin/mv"

    DEF_MODE = 0700
    def __init__(self, server, cfg):
        self.server = server
        self.name = cfg.hostname
        self.root = cfg.root
        self.archive_root = cfg.archive_root
        self.trash_root = cfg.trash_root
        if self.trash_root is None:
            self.trash_root = os.path.join(self.archive_root, ".tilde_trash")

    def __repr__(self):
        return "<ShareUpdater for {0}>".format(self.name)

    def get_real_path(self, homepath, base=None):
        if base is None:
            base = self.root
        #Prevent going out of the share
        shareabs = os.path.abspath(homepath)[1:]
        realpath = os.path.join(base, shareabs)
        return realpath

    def exists(self, path):
        d = defer.Deferred()
        cmd = self.server.runCommand(
            " ".join([self.CMD_TEST, "-e", path]))

        def _exists(reason):
            print reason
            return True

        def _doesnt(reason):
            return False

        cmd.addCallbacks(_exists, _doesnt)
        cmd.chainDeferred(d)

        return d

    def get_path_info(self, path):
        d = defer.Deferred()
        cmd = self.server.runCommand(
            " ".join([self.CMD_STAT, "-c%F:%U:%G:%a", path]),
            protocol=RunCommandProtocol)

        def _parse_out(reason):
            lines = cmd.out.getvalue().splitlines()
            res = dict(zip(("type", "user", "group", "mode"),
                            lines[0].strip().split(":"),
                           ))
            res["mode"] = int(res["mode"], 8)

        def _failed(reason):
            reason.trap(ProcessTerminated)

        cmd.finished.addCallbacks(_parse_out, _failed)
        cmd.finished.chainDeferred(d)
        return d

    def _make_parent(self, path):
        parent = os.path.split(os.path.normpath(path))[0]
        return self.server.runCommand(
            " ".join([self.CMD_MKDIR, "-p", parent])
        ).finished


    def create_home(self, home):
        d = defer.Deferred()
        realpath = self.get_real_path(home.path)
        str_mod = "{0:03o}".format(self.DEF_MODE)
        cmd = [self.CMD_MKDIR,
               "-pm{0}".format(str_mod),
               realpath]

        if home.owner:
            cmd.extend(["&&",
                        self.CMD_CHOWN,
                        "'{0}':'{1}'".format(
                            home.owner,
                            (home.group or '')),
                        realpath])

        cmd.extend(["&&",
                    self.CMD_CHMOD,
                    str_mod,
                    realpath])

        cmd = self.server.runCommand(" ".join(cmd))

        def _success(reason):
            return True

        def _failed(reason):
            reason.trap(ProcessTerminated)
            return False

        cmd.finished.addCallbacks(_success, _failed)
        cmd.finished.chainDeferred(d)
        return d

    def sync(self, fromState, to, home, bwlimit=None):
        if fromState.status == models.HomeState.ACTIVE:
            src_base = self.root
        else:
            src_base = self.archive_root

        sourcepath = self.get_real_path(fromState.path, src_base)
        to_path = to.get_real_path(home.path)

        cmd = [self.CMD_RSYNC, "-rlptgo"]
        if bwlimit:
            cmd.append("--bwlimit={0}".format(bwlimit))

        dest = ":".join([to.name, to_path])
        # Trailing slash on source to prevent copying dir inside itself
        cmd.extend([sourcepath + "/", dest])

        d = to._make_parent(to_path)
        def _then(*r):
            return self.server.runCommand(" ".join(cmd)).finished
        d.addBoth(_then)
        return d

    def archive(self, homestate, toPath):
        if homestate.status != models.HomeState.ACTIVE:
            return defer.fail(Exception("Home must be active to archive"))

        src = self.get_real_path(homestate.path, self.root)
        dst = self.get_real_path(toPath, self.archive_root)
        return self._make_parent(dst).addCallback(lambda *r: self._move(src, dst))

    def move(self, homestate, toPath):
        if homestate.status == models.HomeState.ACTIVE:
            src_dir = self.root
        else:
            src_dir = self.archive_root

        src = self.get_real_path(homestate.path, src_dir)
        dst = self.get_real_path(toPath)
        return self._make_parent(dst).addCallback(lambda *r: self._move(src, dst))

    def _move(self, source, dest):
        args = [self.CMD_MOVE, "-T", "--backup=t", source, dest]
        cmd = self.server.runCommand(" ".join(args),
                                     protocol=RunCommandProtocol)
        def _failed(reason):
            log_err(reason, log,
                "Failed with output: {0} {1}".format(
                    cmd.out.getvalue(), cmd.err.getvalue()),
                reason)
        cmd.finished.addErrback(_failed)
        return cmd.finished


    def remove(self, homestate):
        if homestate.status == models.HomeState.ACTIVE:
            src = self.get_real_path(homestate.path, self.root)
        else:
            src = self.get_real_path(homestate.path, self.archive_root)

        dst = self.get_real_path(homestate.path, self.trash_root)
        return self._make_parent(dst).addCallback(lambda *r: self._move(src, dst))
