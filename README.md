#tilde

Manages home directory life-cycle across multiple servers.

Features:
- Configurable commands
- Handles creating, moving, migrating and archiving homes across servers

## How it works

tilde uses two database tables to track the requested and last known status of
home directories.  It fetches unclean entries periodically and attempts to
update them appropriately.

Authentication is currently limited to ssh key authentication with and between
file servers.

