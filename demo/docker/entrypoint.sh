#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
if [ -d "/opt/venv" ]; then
  export PATH="/opt/venv/bin:$PATH"
fi

# If requirements.txt exists at /app, install (useful when mounting source)
if [ -f /app/requirements.txt ]; then
  pip install -r /app/requirements.txt || true
fi

# Run migrations and create demo superuser
python manage.py migrate --settings=demo.settings
python - <<'PY'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='demo').exists():
    User.objects.create_superuser('demo', 'demo@example.com', 'demopassword')
    print('Created superuser demo/demopassword')
else:
    print('Superuser already exists')
PY

# Populate data
python manage.py shell --settings=demo.settings < demo/populate_demo.py || true

# Default command: runserver
if [ "$#" -eq 0 ]; then
  exec python manage.py runserver 0.0.0.0:8000 --settings=demo.settings
else
  exec "$@"
fi
