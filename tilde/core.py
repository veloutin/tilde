import logging
mlog = logging.getLogger(__name__)
import shutil
import os
import pwd, grp


from tilde.ssh import SSHServer, RunCommandProtocol

from twisted.internet import defer
from twisted.internet.error import ProcessTerminated


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

    def _openCb(self, server, name, config):
        su = ShareUpdater(server, config)

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


class ShareUpdater(object):
    CMD_STAT = "/usr/bin/stat"
    CMD_TEST = "/usr/bin/test"
    CMD_MKDIR = "/usr/bin/mkdir"
    CMD_CHOWN = "/usr/bin/chown"
    CMD_CHMOD = "/usr/bin/chmod"

    DEF_MODE = 0700
    def __init__(self, server, cfg):
        self.server = server
        self.name = cfg.hostname
        self.root = cfg.root
        self.archive_root = cfg.archive_root

    def __repr__(self):
        return "<ShareUpdater for {0}>".format(self.name)

    def get_real_path(self, homepath, base=None):
        if base is None:
            base = self.root
        #Prevent going out of the share
        shareabs = os.path.abspath(homepath)[1:]
        realpath = os.path.join(base, shareabs)
        return realpath


    def uid_to_name(self, uid=None):
        if uid is None:
            uid = os.getuid()
        return pwd.getpwuid(uid).pw_name

    def gid_to_name(self, gid=None):
        if gid is None:
            gid = os.getgid()
        return grp.getgrgid(gid).gr_nam

    def name_to_uid(self, name):
        return pwd.getpwnam(name).pw_uid

    def name_to_gid(self, name):
        return grp.getgrnam(name).gr_gid

    def get_user(self, path):
        return self.uid_to_name(os.stat(path).st_uid)

    def get_group(self, path):
        return self.gid_to_name(os.stat(path).st_gid)

    def update(self, home, state):
        if home.server_name != state.server_name:
            if home.server_name == self.server:
                mlog.debug("req create")
                self.create(home, state)
            elif state.server_name == self.server:
                mlog.debug("req remove")
                self.remove(home, state)
                return

        if home.server_name != self.server:
            mlog.debug(u"bad server {0} != {1}"
                       .format(home.server_name, self.server))
            return

        if home.path != state.path:
            self.move(home, state)

        self.set_perms(home, state)

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
                        "{0}:{1}".format(
                            home.owner.encode("utf-8"),
                            (home.group or u'').encode("utf-8")),
                        realpath])

        cmd.extend(["&&",
                    self.CMD_CHMOD,
                    str_mod,
                    realpath])

        cmd = self.server.runCommand(cmd)

        def _success(reason):
            return True

        def _failed(reason):
            reason.trap(ProcessTerminated)
            return False

        cmd.finished.addCallbacks(_success, _failed)
        cmd.finished.chainDeferred(d)
        return d

    def move(self, home, state):
        old = self.get_real_path(state.path)
        new = self.get_real_path(home.path)
        mlog.info(u"Moving {0} to {1}".format(old, new))
        parent = os.path.split(new)[0]
        if not os.path.exists(parent):
            os.makedirs(parent)
        shutil.move(old, new)
        state.path = home.path

    def remove(self, home, state):
        realpath = self.get_real_path(home.path)
        if os.path.exists(realpath):
            if self.archive_root:
                #Archive all the things!!!!
                archive_path = self.get_real_path(home.path, self.archive_root)
                mlog.info(u"Archiving {0} to {1}".format(
                    realpath, archive_path))
                parent = os.path.split(archive_path)[0]
                if not os.path.exists(parent):
                    os.makedirs(parent)

                suffix = None
                orig_ark = archive_path
                while os.path.exists(archive_path):
                    suffix = suffix + 1 if suffix else 1
                    archive_path = u"{0}{1}".format(orig_ark, suffix)

                shutil.move(realpath, archive_path)

            else:
                shutil.rmtree(realpath)

        else:
            mlog.debug(u"Path does not exist: {0}".format(realpath))

        state.path = None

    def set_perms(self, home, state):
        realpath = self.get_real_path(home.path)
        if not os.path.exists(realpath):
            self.create(home, state)

        if home.owner:
            setuid = home.owner
            numuid = self.name_to_uid(setuid)
        else:
            setuid = None
            numuid = -1

        if home.group:
            setgid = home.group
            numgid = self.name_to_gid(setgid)
        else:
            setgid = None
            numgid = -1

        if setuid or setuid:
            os.chown(realpath, numuid, numgid)
