import urllib.request
import json
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'X-API-Key': 'LightroomMobileWeb1'
}

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode('utf-8')
        if raw.startswith("while (1) {}"):
            raw = raw[len("while (1) {}"):].strip()
        return json.loads(raw)

def get_album_photos(share_id):
    resources_url = f"https://photos.adobe.io/v2/spaces/{share_id}/resources"
    res_data = fetch_json(resources_url)
    resources = res_data.get("resources", [])
    if not resources:
        print(f"No resources for share {share_id}")
        return []
    
    album = resources[0]
    album_name = album.get("payload", {}).get("name", "")
    print(f"Share {share_id} -> Album name: {album_name}")
    
    assets_href = album.get("links", {}).get("/rels/space_album_images_videos", {}).get("href", "")
    base_url = res_data.get("base", "")
    full_assets_url = base_url + assets_href
    print("Fetching assets from:", full_assets_url)
    
    all_assets = []
    next_url = full_assets_url
    while next_url:
        page_data = fetch_json(next_url)
        assets = page_data.get("resources", [])
        all_assets.extend(assets)
        next_rel = page_data.get("links", {}).get("next", {}).get("href")
        if next_rel:
            next_url = page_data.get("base", base_url) + next_rel
        else:
            next_url = None
            
    print(f"Total assets fetched for {share_id}: {len(all_assets)}")
    return all_assets

# Test both shares
# Link 1: 4ab204c0640047bfa7f4c04d38dcdb40
# Link 2: af164dea031e43238136d87761d43e79
assets1 = get_album_photos("4ab204c0640047bfa7f4c04d38dcdb40")
assets2 = get_album_photos("af164dea031e43238136d87761d43e79")

with open("adobe_album_1.json", "w", encoding="utf-8") as f:
    json.dump(assets1, f, ensure_ascii=False, indent=2)

with open("adobe_album_2.json", "w", encoding="utf-8") as f:
    json.dump(assets2, f, ensure_ascii=False, indent=2)

print("Saved adobe_album_1.json and adobe_album_2.json!")
