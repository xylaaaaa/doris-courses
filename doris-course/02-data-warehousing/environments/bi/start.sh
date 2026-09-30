#!/bin/sh
set -eu
superset db upgrade
python /app/course/init_admin.py
superset init
exec gunicorn --bind 0.0.0.0:8088 --workers 2 --threads 2 --timeout 120 'superset.app:create_app()'
