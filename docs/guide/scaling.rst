.. _scaling:

=======================
Scaling & Performance
=======================

If your NekoTab site expects heavy traffic, especially around draw releases and
final tab release, plan scaling ahead of time. Most performance incidents come
from traffic spikes rather than constant baseline load.

Core principles
===============

- Monitor first, scale second.
- Scale web capacity for traffic spikes.
- Keep database and cache health visible.
- Prefer short-term scaling windows to permanent over-provisioning.

What to monitor
===============

Track at least these metrics in your provider dashboard:

- average and p95 response time
- request error rate
- web process CPU and memory
- database connections and saturation
- cache connection count and latency

If response times rise sharply during draw/tab release windows, increase web
capacity before users start refreshing pages repeatedly.

Scaling web capacity
====================

For most deployments, horizontal scaling (more web instances) is the most
effective first step during concurrent traffic spikes.

Typical workflow:

1. Scale up shortly before a known spike (draw release, tab release).
2. Watch response time and error rate for 10-20 minutes.
3. Scale further only if queueing persists.
4. Scale back down after traffic stabilizes.

Caching strategy
================

Caching is critical for public-facing pages that receive bursts of reads.

- Pre-warm high-traffic pages immediately after enabling them.
- Keep short cache timeouts for rapidly changing pages.
- Use longer cache timeouts for stable pages (final tabs, archives).
- If needed, clear cache deliberately and sparingly.

Database and cache limits
=========================

Many performance failures are caused by backend limits rather than CPU.

- ensure database connection limits match your web concurrency
- ensure Redis/cache connection limits are not saturated
- avoid opening unnecessary long-lived backend connections
- verify worker/background processes are not competing with web workloads

Incident response checklist
===========================

When pages become slow or fail to load:

1. Confirm whether it is traffic overload or an application bug.
2. Scale web capacity and verify whether error rate drops.
3. Check database/cache saturation and connection limits.
4. Confirm backups are current before major remediation steps.
5. Communicate status and ETA to tournament staff.

Mirror admin setup (optional)
=============================

For very high-traffic events, some teams maintain a separate admin URL or
restricted admin path so operational users are less affected by public traffic
surges. If you do this, ensure both instances point to the same data services
and test failover before tournament day.