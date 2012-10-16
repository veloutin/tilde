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

import sys
from ConfigParser import SafeConfigParser

import logging
log = logging.getLogger(__name__)

from tilde import commands

class Server(object):
    def __init__(self,
                 hostname,
                 root,
                 user="root",
                 port=22,
                 archive_root=None,
                 trash_root=None,
                 commands=None):
        self.hostname = hostname
        self.root = root
        self.user = user
        self.port = port
        self.archive_root = archive_root
        self.trash_root = trash_root
        self.commands = commands

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

    conf['defaults'] = defaults = {'commands':None}
    if s.has_section('defaults'):
        defaults.update(
            (k, s.get('defaults', k).decode(enc))
            for k in s.options('defaults')
        )

    conf['commands'] = cmds = {"ubuntu":commands.ubuntu}
    for section in [section
                    for section in s.sections()
                    if section.startswith("commands:")]:
        name = section.replace("commands:", "", 1).decode(enc)
        opts = dict(
            (k, s.get(section, k).decode(enc))
            for k in s.options(section)
        )

        inherit = opts.pop("__inherit__", None)

        c = cmds[inherit].copy() if inherit else commands.Commands()
        for k, v in opts.iteritems():
            setattr(c, k, v)

        cmds[name] = c

    for section in [section
                 for section in s.sections()
                 if section.startswith("server:")]:
        name = section.replace("server:", "", 1).decode(enc)
        opts = defaults.copy()
        opts.update(
            (k, s.get(section, k).decode(enc))
            for k in s.options(section)
        )

        if opts["commands"]:
            opts["commands"] = cmds[opts["commands"]]

        opts.setdefault("hostname", name)

        srv[name] = Server(**opts)

    return conf


def setup_environment(cfg):
    from zope.component import getGlobalSiteManager
    from storm.zope.zstorm import ZStorm, IZStorm
    gsm = getGlobalSiteManager()
    ex = gsm.queryUtility(IZStorm)
    if ex:
        for name, store in ex.iterstores():
            ex.remove(store)
            try:
                store.close()
            except Exception:
                log.exception("Failed to close a store")
        gsm.unregisterUtility(ex)

    zs = ZStorm()
    gsm.registerUtility(zs)
    zs.set_default_uri("tilde", cfg["dburl"])
    return cfg
