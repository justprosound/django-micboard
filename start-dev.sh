#!/bin/bash

# Script to start a local development instance with Docker demo

set -e

echo "Setting up virtual environment for development tools..."

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

echo "Installing dev dependencies..."
pip install -r dev-requirements.txt

echo "Validating Django system configuration..."
python manage.py check

echo "Running migrations..."
python manage.py makemigrations micboard
python manage.py migrate

echo "Checking for WSL2 environment and Shure shared key..."
SHARED_KEY=""
if [ -f /proc/version ] && grep -q "WSL2" /proc/version; then
    echo "WSL2 detected. Attempting to read Shure shared key..."
    SHARED_KEY_FILE="/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt"
    if [ -f "$SHARED_KEY_FILE" ]; then
        SHARED_KEY=$(cat "$SHARED_KEY_FILE" | tr -d '\r\n')
        if [ -n "$SHARED_KEY" ]; then
            echo "Found Shure shared key. Will use it for this session."
        else
            echo "Warning: Shared key file exists but appears to be empty."
        fi
    else
        echo "Warning: WSL2 detected but Shure shared key file not found at $SHARED_KEY_FILE"
        echo "Make sure Shure System API is installed and running on Windows."
    fi
else
    echo "Not running in WSL2. Manual configuration of shared key required."
fi

echo "Building demo Docker image..."
cd demo/docker
docker-compose build

echo "Starting demo container..."
echo ""
echo "Demo will be available at: http://localhost:8000"
echo "Make sure your Shure System API is running on port 10000"
echo ""

# Check if shared key is available
if [ -n "$SHARED_KEY" ]; then
    echo "✓ Shared key detected for this session"
    echo "Starting container with shared key..."
    MICBOARD_SHURE_API_SHARED_KEY="$SHARED_KEY" docker-compose up
else
    echo "⚠  WARNING: Shared key not available!"
    echo ""
    echo "For WSL2: Make sure Shure System API is installed and running on Windows."
    echo "For other systems: Set the MICBOARD_SHURE_API_SHARED_KEY environment variable."
    echo ""
    echo "Example:"
    echo "  export MICBOARD_SHURE_API_SHARED_KEY=your-shared-secret-here"
    echo "  ./start-dev.sh"
    echo ""
    echo "Or run directly:"
    echo "  MICBOARD_SHURE_API_SHARED_KEY=your-key-here docker-compose up"
    echo ""
    echo "To get the shared key from Shure System API:"
    echo "  Windows: C:\\ProgramData\\Shure\\SystemAPI\\Standalone\\Security\\sharedkey.txt"
    echo "  Linux/Mac: Check Shure System API logs or configuration"
    echo ""
    echo "Starting container anyway (will fail to connect without shared key)..."
    echo "Press Ctrl+C to stop and configure, or wait for connection errors..."
    echo ""
    docker-compose up
fi
