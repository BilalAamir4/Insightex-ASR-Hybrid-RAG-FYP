#!/usr/bin/env python3
import urllib.request
import json
import time

url = "http://localhost:11434/api/generate"
payload = {
    "model": "qwen3.5:latest",
    "prompt": "Respond with JSON: {\"status\": \"ok\"}",
    "stream": False,
    "format": "json",
    "keep_alive": 0,
    "options": {"num_ctx": 4096}
}
req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode())
    print("KEYS:", list(res.keys()))
    print("RESPONSE:", res.get("response"))
    print("THINKING:", res.get("thinking"))
