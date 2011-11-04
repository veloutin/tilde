from __future__ import unicode_literals

import logging
mlog = logging.getLogger(__name__)

from storm.locals import create_database, Store
from storm.expr import LeftJoin, Or, And

from .models import Home, HomeState
from .core import ShareUpdater


def run(dburl, server, share_root, archive_root):
    mlog.debug("Connecting to {0}".format(dburl))
    store = Store(create_database(dburl))

    mlog.debug("Setting up updater: {0}"
               .format(", ".join([
                   server,
                   share_root,
                   archive_root or "<none>"
               ])))
    updater = ShareUpdater(server, share_root, archive_root)

    requested = store.using(
        Home,
        LeftJoin(
            HomeState,
            And(Home.id == HomeState.id, HomeState.server_name == server)
        )
    ).find((Home, HomeState), Home.server_name == server)

    inactive = store.find(
        (Home, HomeState),
        Home.id == HomeState.id,
        Home.server_name != server,
        HomeState.server_name == server,
    )

    mlog.info("Found {0} shares to update".format(requested.count()))

    for home, state in requested:
        mlog.debug("Updating {0} ({1})".format(home, state))
        if state is None:
            state = HomeState()
            state.home = home

        try:
            updater.update(home, state)
            mlog.debug("- State is now {0}".format(state))
        except Exception:
            mlog.exception("Failed to update home: {0}".format(home))
            store.reload(home)
            if Store.of(state) is store:
                store.reload(state)
            store.rollback()
            continue

        try:
            if Store.of(state) is None:
                store.add(state)
            store.commit()
        except Exception:
            store.rollback()
            mlog.exception("Failed to commit changes")

    mlog.info("Found {0} shares to remove".format(inactive.count()))
    for home, state in inactive:
        mlog.debug("Deactivating {0} ({1})".format(home, state))
        try:
            updater.update(home, state)
            mlog.debug("- State is now {0}".format(state))
        except Exception:
            store.reload(home)
            store.reload(state)
            mlog.exception("Failed to update home: {0}".format(home))
            store.rollback()
            continue

        try:
            #Inactive should mean old state gets flushed
            if state.path is None:
                store.remove(state)
            store.commit()
        except Exception:
            store.rollback()
            mlog.exception("Failed to commit changes")


