.. _upgrading:

=================
Upgrading NekoTab
=================

You generally only need to upgrade instances that are used across multiple
tournaments, or when a bugfix/security release is published.

.. note::

  Upgrading from very old major versions can require additional migration care.
  Always back up before upgrading.

Upgrading a local copy
======================

If you have not made local code changes, upgrading a local install is usually:

1. Download the latest release source.
2. Replace the old source tree.
3. Reinstall dependencies if needed.
4. Run database migrations.
5. Rebuild static assets.

Typical command flow::

    dj migrate
    npm ci
    npm run build
    dj collectstatic

If you use Git locally, you can update your checked-out branch and then run the
same migration/build steps.

Upgrading managed deployments
=============================

For cloud deployments, use your normal deployment pipeline:

1. Update your repository to the target release.
2. Deploy via CI/CD or your standard deploy command.
3. Run migrations in the target environment.
4. Verify health checks and critical workflows.

Recommended safeguards:

- take a database backup before deploying
- stage upgrades in a non-production environment when possible
- review release notes for breaking changes

Upgrading across major versions
===============================

Major version upgrades may include:

- schema migration changes
- removed settings or renamed environment variables
- behavior changes in tournament workflows

Before a major upgrade:

- read release notes carefully
- test with a copy of production data if possible
- validate imports, draw generation, ballots, and notifications

If a major upgrade requires a custom migration path, follow the release notes
for that specific version and keep rollback backups available.