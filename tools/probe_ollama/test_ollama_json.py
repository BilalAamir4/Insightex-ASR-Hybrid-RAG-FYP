import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:11434/api/generate',
    data=json.dumps({
        'model': 'qwen3.5:latest',
        'prompt': 'Provide a JSON object with key "topic" and value "binary search tree".',
        'format': 'json',
        'stream': False
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    print('Keys:', list(res.keys()))
    resp_text = res.get('response', '')
    print('Response text:', repr(resp_text))
    try:
        parsed = json.loads(resp_text)
        print('Parsed successfully:', parsed)
    except Exception as e:
        print('Parse error:', e)

# Unload immediately
urllib.request.urlopen(urllib.request.Request(
    'http://127.0.0.1:11434/api/generate',
    data=json.dumps({'model': 'qwen3.5:latest', 'keep_alive': 0}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
))
print("Unloaded successfully.")
