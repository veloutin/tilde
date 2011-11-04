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
    path = Unicode()
    owner = Unicode()
    group = Unicode(name=u"groupname")
    uuid = Unicode()

    ts = DateTime()

    def __unicode__(self):
        return u"<Home: {0} on {1} ({2}:{3})>".format(
            self.path,
            self.server_name,
            self.owner or u"",
            self.group or u"",
        )

class HomeState(Storm):
    """ State of a home on a server """
    __storm_table__ = u"tilde_home_state"
    __storm_primary__ = u"id", u"server_name"
    id = Int()
    home = Reference(id, Home.id)
    server_name = Unicode()

    path = Unicode()

    def __unicode__(self):
        return u"<HomeState: {0} on {1})>".format(
            self.path,
            self.server_name,
        )
