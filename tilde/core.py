import logging
mlog = logging.get
import os
import pwd, grp


class ShareUpdater(object):
    DEF_MODE = 0511
    def __init__(self, server, share_root, os=os, pwd=pwd, grp=grp):
        self.server = server
        self.root = share_root
        self.os = os
        self.pwd = pwd
        self.grp = grp

    def get_real_path(self, homepath):
        #Prevent going out of the share
        shareabs = self.os.path.abspath(homepath)[1:]
        realpath = self.os.path.join(self.share_root, shareabs)
        return realpath

    def uid_to_name(self, uid=None):
        if uid is None:
            uid = self.os.getuid()
        return self.pwd.getpwuid(uid).pw_name

    def gid_to_name(self, gid=None):
        if gid is None:
            gid = self.os.getgid()
        return self.grp.getgrgid(gid).gr_nam

    def name_to_uid(self, name):
        return self.pwd.getpwnam(name).pw_uid

    def name_to_gid(self, name):
        return self.grp.getgrnam(name).gr_gid

    def get_user(self, path):
        return self.uid_to_name(self.os.stat(path).st_uid)

    def get_group(self, path):
        return self.gid_to_name(self.os.stat(path).st_gid)

    def update(self, home):
        if home.server_changed:
            if home.server_name == self.server:
                self.create(home)
            elif home.cur_server_name == self.server:
                self.remove(home)
            else:
                return

        if home.server_name != self.server:
            return

        if home.path_changed:
            self.move(home)

        self.set_perms(home)


    def create(self, home):
        realpath = self.get_real_path(home.path)
        if self.os.path.exists(realpath):
            if home.owner != self.get_user(realpath):
                raise RuntimeError(
                    u"Refusing to accept existing folder {0} for creation "
                    u"due to conflicting ownership (cur: {1}, req: {2}) "
                    .format(realpath, self.get_user(realpath), home.owner)
                )
        else:
            self.os.makedirs(realpath, self.DEF_MODE)

        home.cur_path = home.path

    def remove(self, home):
        realpath = self.get_real_path(home.path)
        if self.os.path.exists(realpath):
            #Just remove access for now
            self.os.chmod(realpath, 0)

        home.cur_path = None

    def set_perms(self, home):
        realpath = self.get_real_path(home.path)

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
            self.os.chown(realpath, numuid, numgid)
            if setuid:
                home.cur_owner = setuid
            if setgid:
                home.cur_group = setgid


