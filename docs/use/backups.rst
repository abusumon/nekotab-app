.. _backups:

================
Database Backups
================

NekoTab does not include a one-click backup system inside the app itself. Backups
should be created from PostgreSQL directly, or using your hosting provider's
managed snapshot tooling.

You should always create a backup before deleting data in the Edit Database area.
At larger tournaments, it is also good practice to back up at least:

- after generating a draw/allocation
- after entering and confirming round results

Hosted deployments
==================

Most cloud platforms provide at least one of these options:

- scheduled database snapshots
- manual point-in-time snapshots
- direct PostgreSQL dump/restore access

If your provider offers snapshots, use them. Also keep downloadable backups in a
separate location so you can recover even during provider outages.

A portable PostgreSQL backup command looks like this::

    pg_dump --format=custom --no-owner --no-acl -h your_db_host -U your_db_user your_db_name > latest.dump

Local installations
===================

For local PostgreSQL installs, ``pg_dump`` and ``pg_restore`` are recommended.

Create a backup::

    pg_dump --format=custom --no-owner --no-acl -h localhost -U NekoTab yourlocaldb > latest.dump

Restore a backup::

    pg_restore --clean --if-exists --no-owner --no-acl -h localhost -U NekoTab -d yourlocaldb latest.dump

.. _backup-restore-to-local:

Restoring a hosted backup to a local installation
=================================================

A common fallback plan is to restore a hosted backup into a local PostgreSQL
database so you can continue running the tournament offline.

Example workflow::

    createdb frombackup -h localhost -U NekoTab
    pg_restore --no-acl --no-owner -h localhost -U NekoTab -d frombackup latest.dump

Once restored, point your local NekoTab instance at the restored database and
verify that key pages load correctly before going live.