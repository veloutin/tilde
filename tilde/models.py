from storm.database import create_database
from storm.locals import (
    Store,
    Storm,
    Unicode,
    DateTime,
    Reference,
)

def get_store(url):
    return Store(create_database(url))


class Home(Storm):
    """ A home directory """
    __storm_table__ = u"tilde_home"

    server_name = Unicode()
    cur_server_name = Unicode()

    path = Unicode()
    cur_path = Unicode()

    owner = Unicode()
    cur_owner = Unicode()

    group = Unicode()
    cur_group = Unicode()

    external_id = Unicode()

    ts = DateTime()


    @property
    def server_changed(self):
        return self.server_name != self.cur_server_name

    @property
    def path_changed(self):
        return self.path != self.cur_path
