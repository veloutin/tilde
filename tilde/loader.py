import sys
from ConfigParser import SafeConfigParser


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

        srv[opts.setdefault("name", name)] = opts

    return conf
