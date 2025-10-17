Demo project for django-micboard

Quickstart

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

Notes

- `demo.settings` is intentionally minimal and intended for local development only.
- The demo uses the Channels in-memory layer so WebSocket features are available without additional infrastructure.
