#!/bin/bash

# Script to start a local development instance with venv

set -e

echo "Setting up virtual environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing pip-tools..."
pip install pip-tools

echo "Updating requirements files..."
pip-compile --upgrade pyproject.toml -o requirements.txt
pip-compile --upgrade pyproject.toml --extra dev -o dev-requirements.txt
pip-compile --upgrade pyproject.toml --extra docs -o docs/requirements.txt

echo "Installing dependencies..."
pip install -r dev-requirements.txt

echo "Setting up pre-commit hooks..."
pre-commit install

if [ ! -f "manage.py" ]; then
    echo "Creating demo Django project..."
    django-admin startproject demo .

    # Configure settings.py
    sed -i "s/INSTALLED_APPS = \[/INSTALLED_APPS = [\n    'channels',\n    'micboard',\n/" demo/settings.py

    cat >> demo/settings.py << EOF

# Micboard configuration
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': 'http://localhost:8080',
    'SHURE_API_USERNAME': None,
    'SHURE_API_PASSWORD': None,
}

# Channels configuration
ASGI_APPLICATION = 'demo.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    },
}
EOF

    # Configure asgi.py
    cat > demo/asgi.py << EOF
import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from micboard.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
EOF

    mv demo/manage.py .
    rm -rf demo

    echo "Demo project created and configured."
fi

echo "Running migrations..."
python manage.py makemigrations micboard
python manage.py migrate

echo "Starting development server..."
python manage.py runserver
