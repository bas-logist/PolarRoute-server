#!/bin/bash

set -e

python manage.py migrate
python manage.py ensure_adminuser --no-input
python manage.py collectstatic --noinput
python manage.py loaddata locations_bas.json

exec "$@"