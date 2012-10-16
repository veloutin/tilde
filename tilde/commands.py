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

def check_format(name, *keys):
    def _get(self):
        return self[name]
    def _set(self, value):
        try:
            value.format(**dict(zip(keys, keys)))
        except KeyError, e:
            raise ValueError("Unexpected format key", e[0])
        else:
            self[name] = value

    return property(_get, _set, doc="""
        Command to execute for {0}.
        Accepted format keys: {1}""".format(name, keys))

class Commands(dict):
    def __init__(self, **kw):
        for k, v in kw.iteritems():
            setattr(self, k, v)

    def copy(self):
        return Commands(**self)

    stat = check_format("stat", "path")
    test = check_format("test", "path")
    mkdir = check_format("mkdir", "path")
    move = check_format("move", "src_path", "dst_path")
    mkhome = check_format("mkhome", "path", "owner", "group")
    sync = check_format("sync", "src_path", "dst", "dst_path")

ubuntu = Commands(
    stat="/usr/bin/stat -c%F:%U:%G:%a '{path}'",
    test="/usr/bin/test -e '{path}'",
    mkdir="/bin/mkdir -p {path}",
    move="/bin/mv -T --backup=t '{src_path}' '{dst_path}'",
    mkhome=" && ".join((
        "/bin/mkdir -p -m750 '{path}'",
        "/bin/chown '{owner}':'{group}' {path}",
        "/bin/chmod 750 '{path}'",
    )),
    sync="/usr/bin/rsync -rlptgoA '{src_path}/' '{dst}:{dst_path}'",
)
