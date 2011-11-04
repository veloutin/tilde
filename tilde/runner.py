from __future__ import unicode_literals

import logging
mlog = logging.getLogger(__name__)

from storm.locals import create_database, Store
from storm.locals import Or

from .models import Home
from .core import ShareUpdater


def run(dburl, server, share_root, archive_root):
    mlog.debug("Connecting to {0}".format(dburl))
    store = Store(create_database(dburl))

    mlog.debug("Setting up updater: {0}"
               .format(", ".join([server, share_root, archive_root])))
    updater = ShareUpdater(server, share_root, archive_root)

    homes = store.find(
        Home,
        Or(
            Home.server_name == server,
            Home.cur_server_name == server,
        )
    ).order_by(Home.ts)
    mlog.info("Found {0} shares".format(homes.count()))

    for home in homes:
        mlog.debug("Updating {0}".format(home))
        try:
            updater.update(home)
        except Exception:
            store.reload(home)
            mlog.exception("Failed to update home: {0}".format(home))
            continue

        try:
            store.commit()
        except Exception:
            store.rollback()
            mlog.execution("Failed to commit changes")



