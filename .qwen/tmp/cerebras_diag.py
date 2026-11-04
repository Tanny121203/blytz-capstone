import os
import sys
import urllib.request
import json
import django

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

api_key = getattr(settings, "CEREBRAS_API_KEY", "")
key_present = bool(api_key and api_key.strip())

print("CEREBRAS_API_KEY present:", key_present)

url = "https://api.cerebras.ai/v1/models"
req = urllib.request.Request(
    url,
    headers={
        "Authorization": f"Bearer {api_key}" if key_present else "",
        "Content-Type": "application/json",
        "User-Agent": "BlytzClothing/1.0",
    },
    method="GET",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.status
        body = resp.read().decode("utf-8")
        print("HTTP Status:", status)
        data = json.loads(body)
        model_ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        print("Available Models:", model_ids)
except urllib.error.HTTPError as exc:
    status = exc.code
    err_body = exc.read().decode("utf-8", errors="replace")
    print("HTTPError Status:", status)
    try:
        err_json = json.loads(err_body)
        err_obj = err_json.get("error", err_json)
        if isinstance(err_obj, dict):
            print("Error Message:", err_obj.get("message"))
            print("Error Type:", err_obj.get("type"))
            print("Error Code:", err_obj.get("code"))
            print("Error Param:", err_obj.get("param"))
        else:
            print("Error Body:", err_body[:400])
    except Exception:
        print("Error Body:", err_body[:400])
except Exception as e:
    print("Request Exception:", str(e))
