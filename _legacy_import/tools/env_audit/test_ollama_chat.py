import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:11434/api/chat',
    data=json.dumps({
        'model': 'qwen3.5:latest',
        'messages': [{'role': 'user', 'content': 'Output valid JSON with key greeting and value hello'}],
        'format': 'json',
        'stream': False
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    print('Message object:', res.get('message'))

# Unload
urllib.request.urlopen(urllib.request.Request(
    'http://127.0.0.1:11434/api/generate',
    data=json.dumps({'model': 'qwen3.5:latest', 'keep_alive': 0}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
))
