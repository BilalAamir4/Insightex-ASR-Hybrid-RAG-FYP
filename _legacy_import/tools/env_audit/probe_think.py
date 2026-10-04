#!/usr/bin/env python3
import urllib.request
import json

def test(name, payload, endpoint="/api/generate"):
    url = f"http://localhost:11434{endpoint}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print(f"=== {name} ===")
            print("response:", repr(data.get("response", ""))[:200])
            msg = data.get("message", {})
            if msg:
                print("message.content:", repr(msg.get("content", ""))[:200])
                print("message.thinking:", repr(msg.get("thinking", ""))[:200])
            print("thinking:", repr(data.get("thinking", ""))[:200])
    except Exception as e:
        print(f"=== {name} ERROR: {e} ===")

# Test 1: think=False
test("generate think=False", {
    "model": "qwen3.5:latest",
    "prompt": "Output a JSON object with key greeting: {\"greeting\": \"hello\"}",
    "stream": False,
    "format": "json",
    "keep_alive": 0,
    "think": False
})

# Test 2: think=True
test("generate think=True", {
    "model": "qwen3.5:latest",
    "prompt": "Output a JSON object with key greeting: {\"greeting\": \"hello\"}",
    "stream": False,
    "format": "json",
    "keep_alive": 0,
    "think": True
})

# Test 3: chat think=False
test("chat think=False", {
    "model": "qwen3.5:latest",
    "messages": [{"role": "user", "content": "Output a JSON object with key greeting: {\"greeting\": \"hello\"}"}],
    "stream": False,
    "format": "json",
    "keep_alive": 0,
    "think": False
}, endpoint="/api/chat")

# Test 4: chat think=True
test("chat think=True", {
    "model": "qwen3.5:latest",
    "messages": [{"role": "user", "content": "Output a JSON object with key greeting: {\"greeting\": \"hello\"}"}],
    "stream": False,
    "format": "json",
    "keep_alive": 0,
    "think": True
}, endpoint="/api/chat")
