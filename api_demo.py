import requests

BASE = "http://127.0.0.1:5000"

# 1) Public feeds
print("Public feeds:", requests.get(f"{BASE}/api/public/feeds").json())

# 2) Login → token
r = requests.post(f"{BASE}/api/auth/login",
                  json={"username":"admin","password":"hyperdelusionsinallofexistence"})
token = r.json().get("token")
headers = {"Authorization": f"Bearer {token}"}

# 3) List feeds
print("Feeds (before):", requests.get(f"{BASE}/api/feeds", headers=headers).json())

# 4) Add a feed
requests.post(f"{BASE}/api/feeds",
              headers=headers,
              json={"feedUrl":"https://example.com/rss"})
print("Feeds (after add):", requests.get(f"{BASE}/api/feeds", headers=headers).json())

# 5) Remove that feed
requests.delete(f"{BASE}/api/feeds",
                headers=headers,
                json={"feedUrl":"https://example.com/rss"})
print("Feeds (after del):", requests.get(f"{BASE}/api/feeds", headers=headers).json())

# 6) List channels before adding
print("Channels (before):", requests.get(f"{BASE}/api/channels", headers=headers).json())

# 7) Add a new channel (no bot token, defaults to text)
channel_id = "123456789"
r = requests.post(f"{BASE}/api/channels", headers=headers, json={"channelId": channel_id})
print("Add channel response:", r.status_code, r.json())
print("Channels (after add):", requests.get(f"{BASE}/api/channels", headers=headers).json())

# 8) Attempt to add the same channel again (should fail)
r = requests.post(f"{BASE}/api/channels", headers=headers, json={"channelId": channel_id})
print("Add duplicate channel response:", r.status_code, r.json())

# 9) Invalid channelId format
r = requests.post(f"{BASE}/api/channels", headers=headers, json={"channelId": "not_an_int"})
print("Invalid channelId response:", r.status_code, r.json())

# 10) Missing channelId
r = requests.post(f"{BASE}/api/channels", headers=headers, json={})
print("Missing channelId response:", r.status_code, r.json())