#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
if [ -d "/opt/venv" ]; then
  export PATH="/opt/venv/bin:$PATH"
fi

# Run migrations and create demo superuser
python manage.py migrate --settings=demo.settings
python -c "
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
python manage.py shell --settings=demo.settings < demo/populate_demo.py || true

# Start Django Q cluster in background if not already running
if ! pgrep -f "qcluster" > /dev/null; then
    echo "Starting Django Q cluster..."
    python manage.py qcluster --settings=demo.settings &
    sleep 2
fi

# Default command: runserver
if [ "$#" -eq 0 ]; then
  exec python manage.py runserver 0.0.0.0:8000 --settings=demo.settings
else
  exec "$@"
fi
