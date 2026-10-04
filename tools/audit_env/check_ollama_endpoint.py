import urllib.request
import json

url = "http://localhost:11434/api/tags"
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        status = response.status
        body = response.read().decode('utf-8')
        print(f"HTTP Status: {status}")
        data = json.loads(body)
        print("Models found in /api/tags:")
        for m in data.get("models", []):
            print(f" - {m.get('name')} (size: {m.get('size')} bytes)")
except Exception as e:
    print(f"FAILED to reach {url}: {e}")
