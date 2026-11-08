import json
import re

photos = json.load(open('src/data/photos.json', encoding='utf-8'))
album1 = json.load(open('adobe_album_1.json', encoding='utf-8'))
album2 = json.load(open('adobe_album_2.json', encoding='utf-8'))

# Build lookup indices for photos.json
# 1. By exact ID
by_id = {p.get('id'): p for p in photos if p.get('id')}
# 2. By original_filename (lowercased)
by_orig_fn = {p.get('original_filename', '').lower(): p for p in photos if p.get('original_filename')}
# 3. By filename (lowercased)
by_fn = {p.get('filename', '').lower(): p for p in photos if p.get('filename')}
# 4. By base stem without date prefix (e.g. RG7_1437)
by_stem = {}
for p in photos:
    orig = p.get('original_filename', '') or p.get('id', '')
    # match patterns like RG5_1234 or RG7_1234 or 20241010-RG7_1234
    m = re.search(r'(RG[567]_\d+)', orig, re.IGNORECASE)
    if m:
        stem = m.group(1).upper()
        by_stem[stem] = p

print(f"Total photos in gallery: {len(photos)}")
print(f"Total photos in Album 1 (Candidates): {len(album1)}")
print(f"Total photos in Album 2 (Filtered +1): {len(album2)}")

def find_match(asset):
    p = asset.get('asset', {}).get('payload', {})
    fn = (p.get('importSource', {}).get('fileName') or '').strip()
    cd = p.get('captureDate', '')
    
    # 1. Check exact filename
    if fn and fn.lower() in by_orig_fn:
        return by_orig_fn[fn.lower()], "orig_fn"
    if fn and fn.lower() in by_fn:
        return by_fn[fn.lower()], "fn"
    
    # 2. Check stem match (e.g. RG7_1437)
    m = re.search(r'(RG[567]_\d+)', fn, re.IGNORECASE)
    if m:
        stem = m.group(1).upper()
        if stem in by_stem:
            return by_stem[stem], "stem"
            
    # 3. Check by capture date (YYYY:MM:DD HH:MM:SS)
    if cd:
        # cd format: "2024-10-10T08:52:49.440+03:00"
        m_date = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', cd)
        if m_date:
            y, mo, d, h, mi, s = m_date.groups()
            target_exif = f"{y}:{mo}:{d} {h}:{mi}:{s}"
            for p_item in photos:
                pexif = p_item.get('exif', {}).get('date_time_original', '')
                if pexif and pexif.startswith(target_exif):
                    return p_item, "capture_date"
                    
    return None, "none"

matches_album1 = []
missing_album1 = []
for item in album1:
    matched_p, method = find_match(item)
    fn = item.get('asset', {}).get('payload', {}).get('importSource', {}).get('fileName')
    if matched_p:
        matches_album1.append((item, matched_p, method))
    else:
        missing_album1.append(item)

print(f"\nAlbum 1 Matching Results:")
print(f"  Matched already in gallery: {len(matches_album1)} / {len(album1)}")
print(f"  Missing (need to upload):   {len(missing_album1)} / {len(album1)}")

matches_album2 = []
missing_album2 = []
for item in album2:
    matched_p, method = find_match(item)
    if matched_p:
        matches_album2.append((item, matched_p, method))
    else:
        missing_album2.append(item)

print(f"\nAlbum 2 Matching Results:")
print(f"  Matched already in gallery: {len(matches_album2)} / {len(album2)}")
print(f"  Missing (need to upload):   {len(missing_album2)} / {len(album2)}")

if missing_album1:
    print("\nSample missing from Album 1 (first 10):")
    for m in missing_album1[:10]:
        p = m.get('asset', {}).get('payload', {})
        fn = p.get('importSource', {}).get('fileName')
        cd = p.get('captureDate')
        print(f"  fileName={fn}, captureDate={cd}")

if missing_album2:
    print("\nSample missing from Album 2 (first 10):")
    for m in missing_album2[:10]:
        p = m.get('asset', {}).get('payload', {})
        fn = p.get('importSource', {}).get('fileName')
        cd = p.get('captureDate')
        print(f"  fileName={fn}, captureDate={cd}")
