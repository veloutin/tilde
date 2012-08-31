import sys
from ConfigParser import SafeConfigParser


class Server(object):
    def __init__(self,
                 hostname,
                 root,
                 user="root",
                 port=22,
                 archive_root=None,
                 trash_root=None):
        self.hostname = hostname
        self.root = root
        self.user = user
        self.port = port
        self.archive_root = archive_root
        self.trash_root = trash_root

    def __repr__(self):
        return repr(self.__dict__)


def load_config(cfgfile):
    s = SafeConfigParser()
    if not s.read(cfgfile):
        raise Exception("Can't read configfile {0}".format(cfgfile))

    conf = {
        "encoding" : sys.getfilesystemencoding(),
        "sleeptime" : "60",
    }
    conf.update(
        (k, s.get('tilde', k))
        for k in s.options('tilde')
    )

    conf['sleeptime'] = int(conf['sleeptime'])
    enc = conf['encoding']

    conf['servers'] = srv = {}
    for section in [section
                 for section in s.sections()
                 if section.startswith("server:")]:
        name = section.replace("server:", "", 1).decode(enc)
        opts = dict(
            (k, s.get(section, k).decode(enc))
            for k in s.options(section)
        )

        opts.setdefault("hostname", name)

        srv[name] = Server(**opts)

    return conf


def setup_environment(cfg):
    from zope.component import getGlobalSiteManager
    from storm.zope.zstorm import ZStorm
    gsm = getGlobalSiteManager()
    zs = ZStorm()
    gsm.registerUtility(zs)
    zs.set_default_uri("tilde", cfg["dburl"])
