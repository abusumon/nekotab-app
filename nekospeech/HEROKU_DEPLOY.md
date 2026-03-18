# nekospeech — Heroku Deployment Guide

Deploy nekospeech as a **separate Heroku app** that shares the same Postgres
database and Redis instance as the main NekoTab app. The frontend (Django
templates) calls the nekospeech API at its own URL.

---

## 1. Prerequisites

- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed
- Logged in: `heroku login`
- Main NekoTab app already deployed — you know the app name (e.g. `nekotab-prod`)
- Git repo cloned locally

---

## 2. Create the nekospeech Heroku App

```bash
# Create a new app for nekospeech
heroku create nekotab-speech

# Share Postgres from the main app (do NOT create a new addon).
# Both apps must access the same database so they see the same data.
heroku addons:attach nekotab-prod::DATABASE --app nekotab-speech

# Share Redis from the main app.
# nekospeech and the main app use the same Redis for caching and Celery.
heroku addons:attach nekotab-prod::REDISCLOUD --app nekotab-speech
```

> **Why share addons instead of creating new ones?** nekospeech reads and
> writes to the same `speech_events` schema in the same Postgres database
> that Django uses. If you create a separate database, the data won't be
> shared and the app will be unusable. Same for Redis — the Celery worker
> and cache must point to the same instance.

If your main app uses `heroku-redis` instead of `rediscloud`, replace
`REDISCLOUD` above with `REDIS`:

```bash
heroku addons:attach nekotab-prod::REDIS --app nekotab-speech
```

---

## 3. Set Config Vars on the nekospeech App

nekospeech needs the same `DJANGO_SECRET_KEY` that Django uses to sign JWTs.
Both apps must share this value or authentication will fail with 401 errors.

```bash
# Get the secret key from the main app
heroku config:get DJANGO_SECRET_KEY --app nekotab-prod

# Set it on the nekospeech app (paste the value from above)
heroku config:set DJANGO_SECRET_KEY=<value-from-above> --app nekotab-speech

# Set CORS origins to allow requests from your main app's domain
heroku config:set NEKOSPEECH_CORS_ORIGINS=https://nekotab-prod.herokuapp.com --app nekotab-speech
```

If your main app uses a custom domain (e.g. `https://nekotab.app`), use
that instead:

```bash
heroku config:set NEKOSPEECH_CORS_ORIGINS=https://nekotab.app,https://nekotab-prod.herokuapp.com --app nekotab-speech
```

---

## 4. Deploy nekospeech to Heroku

Heroku expects the `Procfile` to be at the root of the repository, but
nekospeech lives in the `nekospeech/` subdirectory. Use `git subtree push`
to push only that subdirectory to the nekospeech Heroku app.

```bash
# Add the nekospeech Heroku app as a remote
heroku git:remote --app nekotab-speech --remote heroku-speech

# Push only the nekospeech/ subdirectory to the nekotab-speech Heroku app
git subtree push --prefix nekospeech heroku-speech main
```

**What `git subtree push` does:** It takes only the contents of the
`nekospeech/` directory and pushes it as if it were the root of the repo.
This means Heroku sees the `Procfile`, `requirements.txt`, and `runtime.txt`
at the root level, which is what it expects.

> If `git subtree push` fails with "Updates were rejected", you can force it:
>
> ```bash
> git push heroku-speech $(git subtree split --prefix nekospeech main):refs/heads/main --force
> ```

After pushing, Heroku will detect the Python buildpack, install dependencies
from `requirements.txt`, and start the `web` process (uvicorn).

---

## 5. Run the SQL Migrations on the Shared Database

The nekospeech schema needs to be created in the shared Postgres database.
You only need to do this once (or when new migrations are added).

Run **all** migrations in order:

```bash
# Migration 001: Create schema + all tables
heroku pg:psql --app nekotab-speech < nekospeech/migrations/001_create_speech_events_schema.sql

# Migration 002: Add ballot_status column to ie_room (required — nekospeech queries this column)
heroku pg:psql --app nekotab-speech < nekospeech/migrations/002_add_ballot_status.sql
```

If `heroku pg:psql` is not available, you can run it from a one-off dyno:

```bash
heroku run "psql \$DATABASE_URL -f migrations/001_create_speech_events_schema.sql" --app nekotab-speech
heroku run "psql \$DATABASE_URL -f migrations/002_add_ballot_status.sql" --app nekotab-speech
```

> **Important:** Both migrations must be run. If you skip 002, nekospeech
> will crash on the first draw or ballot operation because the `ballot_status`
> column is missing from `ie_room`.

---

## 6. Tell the Main NekoTab App Where nekospeech Lives

Set the `NEKOSPEECH_URL` config var on the **main** app so Django templates
inject the correct API URL for the frontend:

```bash
heroku config:set NEKOSPEECH_URL=https://nekotab-speech.herokuapp.com/api/ie --app nekotab-prod
```

This makes the Vue components call `https://nekotab-speech.herokuapp.com/api/ie/…`
instead of the same-origin `/api/ie/…`.

---

## 7. Verify

### Health check

```bash
curl https://nekotab-speech.herokuapp.com/api/ie/health
```

Expected response:

```json
{"status": "ok", "service": "nekospeech"}
```

### Scale the dynos

By default, Heroku may not start all process types. Ensure both `web` and
`worker` are running:

```bash
heroku ps:scale web=1 worker=1 --app nekotab-speech
```

### Test an authenticated endpoint

Open the main NekoTab app in a browser, log in as a tournament admin, and
navigate to the Individual Events page. The page should load events from the
nekospeech API without any CORS or 401 errors.

---

## 8. Troubleshooting

### H10 — App Crashed

The most common Heroku error. Check the logs:

```bash
heroku logs --tail --app nekotab-speech
```

Common causes:
- Missing `DJANGO_SECRET_KEY` — uvicorn can't start because the settings
  validator fails
- Missing Python dependency — check that `requirements.txt` is complete
- Port binding issue — make sure the Procfile uses `$PORT` not a hardcoded port

### 401 Unauthorized on All IE Endpoints

JWT secret mismatch between Django and nekospeech. Verify they're using the
same key:

```bash
# These two values MUST be identical
heroku config:get DJANGO_SECRET_KEY --app nekotab-prod
heroku config:get DJANGO_SECRET_KEY --app nekotab-speech
```

If they differ, update the nekospeech app:

```bash
heroku config:set DJANGO_SECRET_KEY=$(heroku config:get DJANGO_SECRET_KEY --app nekotab-prod) --app nekotab-speech
```

### Database Connection Refused

nekospeech auto-converts `postgres://` to `postgresql+asyncpg://`. If you see
connection errors, check the DATABASE_URL:

```bash
heroku config:get DATABASE_URL --app nekotab-speech
```

It should start with `postgres://` (Heroku's format). nekospeech converts it
automatically. If `DATABASE_URL` is empty, the addon wasn't attached properly:

```bash
heroku addons:attach nekotab-prod::DATABASE --app nekotab-speech
```

### CORS Error in Browser Console

The browser blocks cross-origin requests if CORS isn't configured. Set the
allowed origins on the nekospeech app:

```bash
heroku config:get NEKOSPEECH_CORS_ORIGINS --app nekotab-speech
```

It should contain the main app's URL (e.g. `https://nekotab-prod.herokuapp.com`).
If it's empty or wrong:

```bash
heroku config:set NEKOSPEECH_CORS_ORIGINS=https://nekotab-prod.herokuapp.com --app nekotab-speech
```

After setting this, restart the nekospeech app:

```bash
heroku restart --app nekotab-speech
```
