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

from __future__ import unicode_literals

from datetime import datetime

from storm.database import create_database
from storm.locals import (
    Store,
    Storm,
    Unicode,
    DateTime,
    Reference,
    Int,
)

from storm import tz

def get_store(url):
    return Store(create_database(url))


class Home(Storm):
    """ A home directory """
    __storm_table__ = "tilde_home"
    id = Int(primary=True)

    server_name = Unicode()
    path = Unicode()
    owner = Unicode()
    group = Unicode(name="groupname")
    uuid = Unicode()

    ts = DateTime()

    def __repr__(self):
        return repr(unicode(self))[2:-1]

    def __unicode__(self):
        return "<Home: {0} on {1} ({2}:{3})>".format(
            self.path,
            self.server_name,
            self.owner or "",
            self.group or "",
        )

    def to_json(self):
        return dict(
            id=self.id,
            server_name=self.server_name,
            path=self.path,
            owner=self.owner,
            group=self.group,
            uuid=self.uuid,
            ts=self.ts.isoformat() if self.ts else None
        )

    @property
    def active(self):
        return self.path and self.server_name is not None

    def match(self, status):
        if self.server_name != status.server_name:
            return False

        if self.active:
            return (self.path == status.path and
                    "active" == status.status)
        else:
            return "active" != status.status

    def copy(self):
        h = Home()
        h.id = self.id
        h.path = self.path
        h.server_name = self.server_name
        h.owner = self.owner
        h.group = self.group
        h.uuid = self.uuid
        h.ts = self.ts
        return h



class HomeState(Storm):
    """ State of a home on a server """
    __storm_table__ = "tilde_home_state"
    __storm_primary__ = "id", u"server_name"
    id = Int()
    home = Reference(id, Home.id)
    server_name = Unicode()
    status = Unicode()
    ts = DateTime()

    path = Unicode()

    ACTIVE = "active"
    ARCHIVED = "archived"

    def __repr__(self):
        return repr(unicode(self))[2:-1]

    def __unicode__(self):
        return "<HomeState: {0} on {1} [{2}])>".format(
            self.path,
            self.server_name,
            self.status,
        )

    def to_json(self):
        return dict(
            id=self.id,
            server_name=self.server_name,
            path=self.path,
            status=self.status,
            ts=self.ts.isoformat() if self.ts else None
        )

    def copy(self):
        return self.fromState(self)

    def update(self, other):
        self.id = other.id
        self.path = other.path
        self.server_name = other.server_name
        self.status = other.status
        self.ts = other.ts

    @classmethod
    def fromState(cls, other, **kw):
        new = cls()
        new.update(other)
        for k, v in kw.iteritems():
            setattr(new, k, v)
        return new

    @classmethod
    def fromHome(cls, home, status=ACTIVE, ts=None):
        new = cls()
        new.id = home.id
        new.server_name = home.server_name
        new.path = home.path
        new.status = status
        if ts is None:
            ts = datetime.now().replace(tzinfo=tz.tzlocal())
        new.ts = ts
        return new
