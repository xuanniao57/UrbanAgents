import requests

s = requests.Session()
s.headers.update({'Authorization': 'Bearer 1d983f9a-a745-445b-8313-40a1c8ee6c41'})

r = s.get('http://127.0.0.1:54657/proxies')
proxies = r.json().get('proxies', {})

print("All proxies:")
for name, info in proxies.items():
    print(f"  {name}: {info.get('type', 'unknown')}")
    if info.get('type') == 'Selector':
        print(f"    Now: {info.get('now')}")
        print(f"    All: {info.get('all', [])[:5]}")
