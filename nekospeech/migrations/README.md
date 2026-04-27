# nekospeech SQL Migrations

## 001 — Create `speech_events` schema

This migration creates the `speech_events` PostgreSQL schema and all Individual
Events (IE) tables used by the nekospeech service.  Django never writes to this
schema — it is owned entirely by nekospeech.

### Tables created

| Table | Purpose |
|-------|---------|
| `speech_events.speech_event` | One row per IE event type per tournament |
| `speech_events.ie_entry` | One row per competitor in an event |
| `speech_events.ie_room` | One room per round (holds entries + judge) |
| `speech_events.ie_room_entry` | M2M join between rooms and entries |
| `speech_events.ie_result` | Judge ballot line — rank + speaker points |

Custom enum types: `speech_events.event_type`, `speech_events.tiebreak_method`,
`speech_events.scratch_status`.

---

### 1. Run in development (local Docker Postgres)

```bash
# From the repo root, with Docker Compose running:
docker compose exec db psql -U NekoTab -d NekoTab \
  -f /docker-entrypoint-initdb.d/001_create_speech_events_schema.sql
```

If the SQL file isn't mounted into the container, copy it first:

```bash
docker compose cp nekospeech/migrations/001_create_speech_events_schema.sql db:/tmp/001.sql
docker compose exec db psql -U NekoTab -d NekoTab -f /tmp/001.sql
```

### 2. Run in production (hosted Postgres)

```bash
# Option A: Use psql with your production DATABASE_URL
psql "$DATABASE_URL" -f nekospeech/migrations/001_create_speech_events_schema.sql

# Option B: Use your provider's external connection string
psql "postgres://user:pass@host:port/dbname" \
  -f nekospeech/migrations/001_create_speech_events_schema.sql
```

### 3. Verify the migration ran correctly

Connect to your database and run:

```sql
-- Check the schema exists
SELECT schema_name
  FROM information_schema.schemata
 WHERE schema_name = 'speech_events';

-- Check all five tables exist
SELECT table_name
  FROM information_schema.tables
 WHERE table_schema = 'speech_events'
 ORDER BY table_name;
```

Expected output (5 rows):

```
 table_name
-----------
 ie_entry
 ie_result
 ie_room
 ie_room_entry
 speech_event
```

### 4. Roll back (DESTRUCTIVE — use with caution)

> **⚠️  WARNING:** This will permanently delete ALL Individual Events data —
> events, entries, rooms, results, and custom enum types.  There is no undo.
> Back up your data first if you need it.

```sql
DROP SCHEMA speech_events CASCADE;
```

After rolling back, you must re-run the migration to restore the schema.
