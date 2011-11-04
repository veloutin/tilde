import logging
mlog = logging.getLogger(__name__)
import shutil
import os
import pwd, grp


class ShareUpdater(object):
    DEF_MODE = 0700
    def __init__(self, server, share_root, archive_root=None):
        self.server = server
        self.root = share_root
        self.archive_root = archive_root

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

    def update(self, home):
        if home.server_changed:
            if home.server_name == self.server:
                mlog.debug("req create")
                self.create(home)
            elif home.cur_server_name == self.server:
                mlog.debug("req remove")
                self.remove(home)
                return

        if home.server_name != self.server:
            mlog.debug(u"bad server {0} != {1}"
                       .format(home.server_name, self.server))
            return

        if home.path_changed:
            self.move(home)

        self.set_perms(home)


    def create(self, home):
        realpath = self.get_real_path(home.path)
        if os.path.exists(realpath):
            mlog.debug(u"Path exists: {0}".format(realpath))
            if home.owner != self.get_user(realpath):
                raise RuntimeError(
                    u"Refusing to accept existing folder {0} for creation "
                    u"due to conflicting ownership (cur: {1}, req: {2}) "
                    .format(realpath, self.get_user(realpath), home.owner)
                )
        else:
            mlog.info(u"makedirs: {0}".format(realpath))
            os.makedirs(realpath, self.DEF_MODE)

        home.cur_server_name = self.server
        home.cur_path = home.path

    def move(self, home):
        old = self.get_real_path(home.cur_path)
        new = self.get_real_path(home.path)
        mlog.info(u"Moving {0} to {1}".format(old, new))
        parent = os.path.split(new)[0]
        if not os.path.exists(parent):
            os.makedirs(parent)
        shutil.move(old, new)
        home.cur_path = home.path

    def remove(self, home):
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
                shutil.move(realpath, archive_path)

            else:
                shutil.rmtree(realpath)

        else:
            mlog.debug(u"Path does not exist: {0}".format(realpath))

        home.cur_server_name = None
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
            os.chown(realpath, numuid, numgid)
            if setuid:
                home.cur_owner = setuid
            if setgid:
                home.cur_group = setgid


