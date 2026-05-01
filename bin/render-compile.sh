#!/usr/bin/env bash
# exit on error
set -o errexit

echo "-----> Install dependencies"
python -m pip install pipenv
pipenv install --system

echo "-----> I'm post-compile hook"

echo "-----> Running database migration"
python manage.py migrate --noinput

echo "-----> Ensuring Google OAuth SocialApp"
python manage.py ensure_google_socialapp || true

echo "-----> Running dynamic preferences checks"
python manage.py checkpreferences

echo "-----> Running static asset compilation"
npm install
npm run build

echo "-----> Running static files compilation"
python manage.py collectstatic --noinput --ignore='*.bak'

echo "-----> Post-compile done"
