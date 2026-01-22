#!/usr/bin/env bash
set -euo pipefail

# uv handles environment

# Run migrations and create demo superuser
uv run manage.py migrate --settings=demo.settings
uv run python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='demo').exists():
    User.objects.create_superuser('demo', 'demo@example.com', 'demopassword')
    print('Created superuser demo/demopassword')
else:
    print('Superuser already exists')
"

# Populate data
uv run manage.py shell --settings=demo.settings < demo/populate_demo.py || true

# Start Django Q cluster in background if not already running
if ! pgrep -f "qcluster" > /dev/null; then
    echo "Starting Django Q cluster..."
    uv run manage.py qcluster --settings=demo.settings &
    sleep 2
fi

# Default command: runserver
if [ "$#" -eq 0 ]; then
  exec uv run manage.py runserver 0.0.0.0:8000 --settings=demo.settings
else
  exec "$@"
fi
