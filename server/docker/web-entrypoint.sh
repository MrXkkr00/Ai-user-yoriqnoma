#!/bin/sh
# Web container start: database migrations, then gunicorn.
set -e
python manage.py migrate --noinput
exec gunicorn yoriqnoma_server.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --forwarded-allow-ips="*" \
    --access-logfile -
