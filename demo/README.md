Demo project for django-micboard

## Quickstart

### Local Development

1. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt -r dev-requirements.txt
```

2. Run initial migrations and create a superuser

```bash
python manage.py migrate --settings=demo.settings
python manage.py createsuperuser --settings=demo.settings
```

3. Populate demo data (optional)

```bash
python manage.py shell --settings=demo.settings < demo/populate_demo.py
```

4. Run the development server

```bash
python manage.py runserver --settings=demo.settings
```

### Docker Demo

For a standalone demo using Docker:

```bash
cd demo/docker
docker-compose up --build
```

The demo will be available at http://localhost:8000 with superuser `demo/demopassword`.

## Connecting to Local Shure System API

### Windows Docker Desktop

When running the demo container on Windows Docker Desktop and you want to connect to a Shure System API running on your Windows host:

1. **Install and configure Shure System API** on your Windows machine
   - Download from: https://www.shure.com/en-US/products/software/systemapi
   - Install and start the service (typically runs on port 10000)

2. **Configure Windows Firewall** (if needed)
   - Allow inbound connections on port 10000
   - Or temporarily disable firewall for testing

3. **Configure Shure System API** to accept connections
   - Open Shure System API configuration
   - Ensure it's bound to `0.0.0.0` or your network interface (not just localhost)
   - Check that the API is accessible at `http://localhost:10000` from your Windows machine

4. **Run the demo with host networking**
   ```bash
   cd demo/docker
   docker-compose up --build
   ```

   The docker-compose.yml is pre-configured to use `host.docker.internal:10000` to reach your Windows host.

5. **Verify connection**
   - Check the demo logs for connection errors
   - The demo should automatically detect and display your Shure devices

### Linux/macOS Docker

For Linux or macOS, the container can reach the host using `host.docker.internal` or the gateway IP:

```bash
# Set the environment variable
export MICBOARD_SHURE_API_BASE_URL=http://host.docker.internal:10000

# Or find your host IP
# ip route show default | awk '{print $3}':10000

cd demo/docker
docker-compose up --build
```

### Manual Configuration

You can also override the Shure API URL by setting the environment variable:

```bash
# For Windows Docker Desktop
export MICBOARD_SHURE_API_BASE_URL=http://host.docker.internal:10000

# For Linux/macOS
export MICBOARD_SHURE_API_BASE_URL=http://172.17.0.1:10000

# Required: Set the shared secret from your Shure System API
export MICBOARD_SHURE_API_SHARED_KEY=your-shared-secret-here

# Run the container
cd demo/docker
docker-compose up --build
```

### Troubleshooting

**Connection refused errors:**
- Ensure Shure System API is running on your host
- Check that it's listening on the correct port (default: 10000)
- Verify firewall settings allow connections

**Empty device list:**
- Check Shure System API logs for errors
- Ensure your Shure devices are connected and recognized by the API
- Verify the shared secret is correctly configured

**SSL certificate errors:**
- If using HTTPS with self-signed certificates, disable SSL verification:
  ```bash
  export MICBOARD_SHURE_API_VERIFY_SSL=false
  ```
- ⚠️ **Security Warning**: Only disable SSL verification for testing with self-signed certificates
- For production, use valid SSL certificates and keep verification enabled

**HTTPS connections:**
- The Shure System API supports HTTPS connections
- Update your API URL to use `https://` and port 10000
- Ensure SSL certificates are valid or disable verification for self-signed certs

## Notes

- `demo.settings` is intentionally minimal and intended for local development only.
- The demo uses the Channels in-memory layer so WebSocket features are available without additional infrastructure.
- For production use, configure proper database, Redis for Channels, and secure settings.
