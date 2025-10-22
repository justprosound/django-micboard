import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django
from django.test import Client

django.setup()


def main():
    client = Client()
    payload = {"ips": ["192.0.2.1"], "manufacturer": "shure"}
    resp = client.post(
        "/api/discovery/add-ips/", json.dumps(payload), content_type="application/json"
    )
    print("STATUS:", resp.status_code)
    print("CONTENT:", resp.content)


if __name__ == "__main__":
    main()
