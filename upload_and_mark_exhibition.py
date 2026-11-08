#!/usr/bin/env python3
"""
upload_and_mark_exhibition.py
=============================
1. Matches exhibition candidates from Adobe Lightroom Albums:
   - Link 1 (Album 1): Candidates (196 photos) -> score = 1
   - Link 2 (Album 2): Further selection / +1 (121 photos) -> score = 2
2. Downloads the 75 missing photos directly from Lightroom Web API in 2048px resolution.
3. Generates Display WebP (max 2048px Q100) and Thumbnail WebP (max 500px Q80).
4. Uploads to Cloudflare R2 bucket.
5. Extracts technical EXIF from Lightroom XMP / metadata.
6. Runs AI batch tagging via Gemini (bilingual + species registry + humor).
7. Updates all 196 exhibition candidates in photos.json:
   - is_exhibition_candidate: True
   - exhibition_score: 2 (if in Link 2) or 1 (if in Link 1)
   - exhibition: {"candidate": True, "score": 2 | 1}
"""

import io
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from match_exhibition_photos import find_match
from process_photos import (
    R2Uploader,
    AITagger,
    clean_safe_id,
    sanitize_text,
    format_shutter_speed,
    format_aperture,
    format_focal_length,
    format_camera_model,
    DISPLAY_QUALITY,
    THUMB_QUALITY,
    THUMB_MAX_WIDTH,
    PROJECT_ROOT,
    DEFAULT_DISPLAY_DIR,
    DEFAULT_THUMBS_DIR,
    DEFAULT_DATA_FILE,
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)',
    'X-API-Key': 'LightroomMobileWeb1'
}

def extract_exif_from_adobe_payload(payload: dict) -> dict:
    """Extract and format EXIF metadata from Lightroom XMP payload."""
    xmp = payload.get('xmp', {})
    tiff = xmp.get('tiff', {})
    exif = xmp.get('exif', {})
    
    # Camera Model
    make = tiff.get('Make')
    model = tiff.get('Model')
    camera_model = format_camera_model(make, model)
    if not camera_model and model:
        camera_model = str(model)
        
    # Lens Model
    lens_model = exif.get('LensModel') or xmp.get('aux', {}).get('Lens') or tiff.get('LensModel')
    if lens_model and isinstance(lens_model, str):
        lens_model = lens_model.strip()
    else:
        lens_model = None

    # Focal Length
    raw_focal = exif.get('FocalLength')
    focal_length = format_focal_length(raw_focal)
    
    # Aperture (FNumber)
    raw_fnum = exif.get('FNumber') or exif.get('ApertureValue')
    aperture = format_aperture(raw_fnum)
    
    # Shutter Speed (ExposureTime)
    raw_exp = exif.get('ExposureTime') or exif.get('ShutterSpeedValue')
    shutter_speed = format_shutter_speed(raw_exp)
    
    # ISO
    raw_iso = exif.get('ISOSpeedRatings')
    iso = None
    if raw_iso:
        if isinstance(raw_iso, list) and len(raw_iso) > 0:
            try: iso = int(raw_iso[0])
            except: iso = None
        else:
            try: iso = int(raw_iso)
            except: iso = None
            
    # Capture Date: e.g. "2024-11-20T08:26:27.310+02:00" -> "2024:11:20 08:26:27"
    raw_cd = payload.get('captureDate', '') or exif.get('DateTimeOriginal', '')
    date_time_original = None
    if raw_cd:
        m = re.match(r'(\d{4})[:\-](\d{2})[:\-](\d{2})[T\s](\d{2}):(\d{2}):(\d{2})', str(raw_cd))
        if m:
            date_time_original = f"{m.group(1)}:{m.group(2)}:{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
        else:
            date_time_original = str(raw_cd)[:19]

    return {
        "camera_model": camera_model,
        "lens_model": lens_model,
        "focal_length": focal_length,
        "aperture": aperture,
        "shutter_speed": shutter_speed,
        "iso": iso,
        "date_time_original": date_time_original,
    }

def main():
    photos_path = DEFAULT_DATA_FILE
    with open(photos_path, 'r', encoding='utf-8') as f:
        photos = json.load(f)

    album1 = json.load(open('adobe_album_1.json', encoding='utf-8')) # Link 1 (196 items)
    album2 = json.load(open('adobe_album_2.json', encoding='utf-8')) # Link 2 (121 items)

    # Asset IDs in Album 2 (+1)
    album2_asset_ids = {item['asset']['id'] for item in album2}

    print(f"Loaded {len(photos)} gallery photos.")
    print(f"Loaded {len(album1)} photos from Link 1 (Candidates).")
    print(f"Loaded {len(album2)} photos from Link 2 (Filtered +1).")

    # Match each item from Album 1
    matched_photos_map = {} # photo_id -> (item, score)
    missing_items = []      # list of (item, score)

    for item in album1:
        asset_id = item['asset']['id']
        score = 2 if asset_id in album2_asset_ids else 1
        matched_p, method = find_match(item)
        if matched_p:
            matched_photos_map[matched_p['id']] = (item, score)
        else:
            missing_items.append((item, score))

    print(f"\nMatching Summary:")
    print(f"  Existing photos to update: {len(matched_photos_map)}")
    print(f"  Missing photos to process & upload: {len(missing_items)}")

    # Initialize R2 and AI Tagger
    r2 = R2Uploader()
    if r2.is_configured:
        print(f"Cloudflare R2 is configured: bucket='{r2.bucket_name}'.")
    else:
        print("WARNING: Cloudflare R2 is not configured!")

    ai_tagger = AITagger()
    print(f"AI Tagger available: {ai_tagger.is_available}")

    existing_ids = {p.get('id') for p in photos if p.get('id')}
    local_source_dir = Path(r"C:\Users\Roi\Pictures\תמונות לאתר")
    if local_source_dir.exists():
        print(f"Will archive downloaded originals to {local_source_dir}")

    DEFAULT_DISPLAY_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    # Process missing items in batches
    BATCH_SIZE = 5
    new_records = []
    
    print("\n--- Starting Download & Processing for Missing Photos ---")
    for b_start in range(0, len(missing_items), BATCH_SIZE):
        batch = missing_items[b_start:b_start + BATCH_SIZE]
        batch_num = (b_start // BATCH_SIZE) + 1
        total_batches = (len(missing_items) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"\nProcessing Batch {batch_num}/{total_batches} ({len(batch)} photos)...")

        prepared_batch = []
        for item, score in batch:
            asset = item['asset']
            payload = asset.get('payload', {})
            import_source = payload.get('importSource', {})
            fn = (import_source.get('fileName') or f"{asset['id']}.jpg").strip()
            
            # Clean filename and build safe ID
            cd_raw = payload.get('captureDate', '')
            date_prefix = ""
            if cd_raw:
                m_d = re.match(r'(\d{4})[:\-](\d{2})[:\-](\d{2})', str(cd_raw))
                if m_d:
                    date_prefix = f"{m_d.group(1)}{m_d.group(2)}{m_d.group(3)}-"
            
            clean_stem = Path(fn).stem
            clean_stem = re.sub(r'[\(\)\s]+', '_', clean_stem).strip('_')
            proposed_id = f"{date_prefix}{clean_stem}" if date_prefix and not clean_stem.startswith(date_prefix) else clean_stem
            safe_id = clean_safe_id(proposed_id, existing_ids)
            existing_ids.add(safe_id)

            # Download 2048px rendition
            rel_2048 = asset['links']['/rels/rendition_type/2048']['href']
            download_url = "https://photos.adobe.io/v2/spaces/4ab204c0640047bfa7f4c04d38dcdb40/" + rel_2048

            img_bytes = None
            for retry in range(3):
                try:
                    req = urllib.request.Request(download_url, headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        img_bytes = resp.read()
                    break
                except Exception as e:
                    print(f"  Retry {retry+1} downloading {fn}: {e}")
                    time.sleep(2)

            if not img_bytes:
                print(f"  ERROR: Could not download {fn}. Skipping.")
                continue

            # Open image with Pillow
            img = Image.open(io.BytesIO(img_bytes))
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Save original to local archive if folder exists
            if local_source_dir.exists():
                local_arch_path = local_source_dir / f"{safe_id}.jpg"
                if not local_arch_path.exists():
                    try:
                        with open(local_arch_path, "wb") as f_arch:
                            f_arch.write(img_bytes)
                    except Exception as e:
                        print(f"  Could not archive {safe_id}.jpg locally: {e}")

            # Generate Display WebP
            display_filename = f"{safe_id}.webp"
            display_local_path = DEFAULT_DISPLAY_DIR / display_filename
            display_buf = io.BytesIO()
            img.save(display_buf, format="WEBP", quality=DISPLAY_QUALITY, method=4)
            display_bytes = display_buf.getvalue()
            with open(display_local_path, "wb") as f_out:
                f_out.write(display_bytes)

            # Generate Thumbnail WebP
            thumb_filename = f"{safe_id}.webp"
            thumb_local_path = DEFAULT_THUMBS_DIR / thumb_filename
            w, h = img.size
            if w > THUMB_MAX_WIDTH:
                thumb_w = THUMB_MAX_WIDTH
                thumb_h = round((h * thumb_w) / w)
                thumb_img = img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            else:
                thumb_img = img.copy()

            thumb_buf = io.BytesIO()
            thumb_img.save(thumb_buf, format="WEBP", quality=THUMB_QUALITY, method=4)
            thumb_bytes = thumb_buf.getvalue()
            with open(thumb_local_path, "wb") as f_out:
                f_out.write(thumb_bytes)

            # Upload to Cloudflare R2
            display_url = None
            thumb_url = None
            if r2.is_configured:
                display_url = r2.upload_file(display_local_path, f"photos/display/{display_filename}", "image/webp")
                thumb_url = r2.upload_file(thumb_local_path, f"photos/thumbs/{thumb_filename}", "image/webp")

            # Extract EXIF from Adobe XMP payload
            exif_meta = extract_exif_from_adobe_payload(payload)

            dimensions = {
                "width": img.width,
                "height": img.height,
                "aspect_ratio": round(img.width / img.height, 3) if img.height else 1.5
            }

            paths = {
                "display": display_url or f"/photos/display/{display_filename}",
                "thumbnail": thumb_url or f"/photos/thumbs/{thumb_filename}"
            }

            prepared_batch.append({
                "id": safe_id,
                "filename": display_filename,
                "original_filename": fn,
                "display_url": display_url,
                "thumb_url": thumb_url,
                "paths": paths,
                "dimensions": dimensions,
                "exif": exif_meta,
                "score": score,
                "thumb_img": thumb_img,
                "item": item
            })

        # Run AI Batch Tagging for the batch
        if prepared_batch:
            if ai_tagger.is_available:
                tag_inputs = [(p["thumb_img"], p["original_filename"]) for p in prepared_batch]
                ai_results = ai_tagger.tag_batch(tag_inputs)
            else:
                ai_results = [ai_tagger._fallback_tags(p["original_filename"]) for p in prepared_batch]
            
            for p, ai_tags in zip(prepared_batch, ai_results):
                rec = {
                    "id": p["id"],
                    "filename": p["filename"],
                    "original_filename": p["original_filename"],
                    "display_url": p["display_url"],
                    "thumb_url": p["thumb_url"],
                    "paths": p["paths"],
                    "dimensions": p["dimensions"],
                    "exif": p["exif"],
                    "ai": ai_tags.model_dump(),
                    "processed_at": datetime.now().isoformat(),
                    "last_edited_at": None,
                    "is_featured": (p["score"] == 2),
                    "is_exhibition_candidate": True,
                    "exhibition_score": p["score"],
                    "exhibition": {
                        "candidate": True,
                        "score": p["score"],
                        "shortlisted": (p["score"] == 2)
                    }
                }
                new_records.append(rec)
                print(f"  + Added: {rec['id']} | Title: {ai_tags.title} | Species: {ai_tags.species_hebrew} | Score: {p['score']}")

        time.sleep(1)

    print(f"\nFinished uploading & tagging {len(new_records)} new photos.")

    # Now add new records to photos.json and update existing ones
    photos.extend(new_records)
    print(f"Total photos now in list: {len(photos)}")

    # Update all photos with exhibition fields
    updated_existing_count = 0
    candidate_1_count = 0
    candidate_2_count = 0

    for p in photos:
        pid = p.get('id')
        if pid in matched_photos_map:
            item, score = matched_photos_map[pid]
            p["is_exhibition_candidate"] = True
            p["exhibition_score"] = score
            p["exhibition"] = {
                "candidate": True,
                "score": score,
                "shortlisted": (score == 2)
            }
            updated_existing_count += 1
            if score == 2:
                candidate_2_count += 1
            else:
                candidate_1_count += 1
        elif p.get("is_exhibition_candidate") is True:
            # New record already marked
            score = p.get("exhibition_score", 1)
            if score == 2:
                candidate_2_count += 1
            else:
                candidate_1_count += 1
        else:
            p["is_exhibition_candidate"] = False
            p["exhibition_score"] = 0
            p["exhibition"] = {
                "candidate": False,
                "score": 0,
                "shortlisted": False
            }

    print(f"\nExhibition Metadata Summary in photos.json:")
    print(f"  Existing photos marked: {updated_existing_count}")
    print(f"  New photos added & marked: {len(new_records)}")
    print(f"  Total Candidate photos (Score >= 1): {candidate_1_count + candidate_2_count}")
    print(f"    - Link 1 Only (Score = 1): {candidate_1_count}")
    print(f"    - Link 2 / +1 Shortlist (Score = 2): {candidate_2_count}")

    with open(photos_path, 'w', encoding='utf-8') as f:
        json.dump(photos, f, ensure_ascii=False, indent=2)

    print(f"Saved updated {photos_path} successfully!")

if __name__ == "__main__":
    main()
