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
echo "Installing dev dependencies..."
pip install -r dev-requirements.txt
echo "Installing docs dependencies..."
pip install -r docs/requirements.txt

echo "Validating Django system configuration..."
python manage.py check

echo "Running migrations..."
python manage.py makemigrations micboard
python manage.py migrate

# echo "Starting development server..."
# python manage.py runserver
