#!/bin/sh
# Apply migrations before serving. Safe to repeat: migrate is idempotent, and
# with SQLite the container is the only writer at this point.
set -e

echo "==> applying migrations"
python manage.py migrate --noinput

exec "$@"
