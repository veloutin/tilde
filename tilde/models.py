from storm.database import create_database
from storm.locals import (
    Store,
    Storm,
    Unicode,
    DateTime,
    Reference,
    Int,
)

def get_store(url):
    return Store(create_database(url))


class Home(Storm):
    """ A home directory """
    __storm_table__ = u"tilde_home"
    id = Int(primary=True)

    server_name = Unicode()
    cur_server_name = Unicode()

    path = Unicode()
    cur_path = Unicode()

    owner = Unicode()
    cur_owner = Unicode()

    group = Unicode(name=u"groupname")
    cur_group = Unicode(name=u"cur_groupname")

    uuid = Unicode()

    ts = DateTime()

    def __unicode__(self):
        return u"<Home: {0} on {1} ({2}:{3})>".format(
            self.server_name,
            self.path,
            self.owner or u"",
            self.group or u"",
        )

    @property
    def server_changed(self):
        return self.server_name != self.cur_server_name

    @property
    def path_changed(self):
        return self.path != self.cur_path
