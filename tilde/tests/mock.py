import os
import pwd
import grp

class MockDB(object):
    def __init__(self, values=(("root", 0),)):
        self.name_to_id = dict(values)
        self.id_to_name = dict(
            (v, k) for k, v in self.name_to_id.iteritems()
        )

class MockPwd(MockDB):
    def getpwuid(self, uid):
        name = self.id_to_name[uid]
        return pwd.struct_pwent(
            [name, 'x', uid, 0, uid, '/nonexistant', '/bin/false']
        )

    def getpwnam(self, name):
        uid = self.name_to_id[name]
        return pwd.struct_pwent(
            [name, 'x', uid, 0, uid, '/nonexistant', '/bin/false']
        )



class MockGrp(MockDB):

    def getgrnam(self, name):
        gid = self.name_to_id[name]
        return grp.struct_group(
            [name, '*', gid, []]
        )
    def getgrgid(self, gid):
        name = self.id_to_name[gid]
        return grp.struct_group(
            [name, '*', gid, []]
        )



class MockOS(object):
    def __init__(self):
        self.owns = {}

    def __getattr__(self, name):
        return getattr(os, name)

    def chown(self, path, uid, gid):
        self.owns[path] = (uid, gid)
