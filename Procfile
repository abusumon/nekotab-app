# Production

# Note that this runs honcho, which in turn runs a second 'MultiProcfile'
# This better allows for multiple processes to be run simultaneously

web: honcho -f ProcfileMulti start
worker: python manage.py runworker notifications adjallocation venues
release: python manage.py migrate --noinput && (python manage.py checkpreferences || true)
nekospeech: cd nekospeech && uvicorn nekospeech.main:app --host 0.0.0.0 --port $PORT
nekospeech-worker: cd nekospeech && celery -A nekospeech.workers.tasks worker --loglevel=info
