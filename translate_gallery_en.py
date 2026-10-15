#!/usr/bin/env python3
"""
translate_gallery_en.py
=======================
הוספת שכבת אנגלית מלאה לכל התמונות בגלריה:
- species_en: נמשך ישירות ממאגר השמות הטקסונומי הרשמי (species_registry.json).
- title_en, description_en, humorous_description_en, tags_en: מיוצרים באמצעות Gemini Flash-Lite.
- שמירה על כלל הברזל: אם אין הומור בעברית, humorous_description_en נשאר ריק ("").
- שמירה אינקרמנטלית רציפה לתוך photos.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent
PHOTOS_FILE = PROJECT_ROOT / "src" / "data" / "photos.json"
REGISTRY_FILE = PROJECT_ROOT / "src" / "data" / "species_registry.json"


def sanitize_text(text: Optional[str]) -> str:
    """ניקוי מחרוזות מסימני bidi, רווחים כפולים ומרכאות מעטפת."""
    if not text:
        return ""
    t = re.sub(r"[\u200e\u200f\u202a-\u202e\ufeff\u200b\ufffd]", "", str(text))
    t = re.sub(r"^[\"\'\`\*\_\#\s]+|[\"\'\`\*\_\#\s]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class PhotoTranslationItem(BaseModel):
    id: str = Field(description="מזהה התמונה הייחודי")
    title_en: str = Field(description="Natural, evocative English title (no quotes)")
    description_en: str = Field(description="Natural, descriptive English sentence describing the scene/subject")
    humorous_description_en: str = Field(
        default="",
        description="Witty English caption ONLY if Hebrew humorous description exists. If Hebrew humor is empty, MUST be empty string!"
    )
    tags_en: List[str] = Field(default_factory=list, description="3-6 lowercase English tags for searching/filtering")


class BatchTranslationResponse(BaseModel):
    translations: List[PhotoTranslationItem]


def load_registry() -> Dict[str, dict]:
    """טעינת מילון המינים לחיפוש מהיר לפי שם מדעי לטיני או שם עברי."""
    if not REGISTRY_FILE.exists():
        return {"by_latin": {}, "by_hebrew": {}}
    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "by_latin": {k.lower().strip(): v for k, v in data.get("by_latin", {}).items()},
        "by_hebrew": {k.strip(): v for k, v in data.get("by_hebrew", {}).items()},
    }


def lookup_species_en(ai: dict, registry: dict) -> str:
    """שליפת השם האנגלי הרשמי ממאגר השמות."""
    la = (ai.get("species_latin") or "").strip().lower()
    he = (ai.get("species_hebrew") or "").strip()
    
    if la and la in registry["by_latin"]:
        return registry["by_latin"][la].get("english", "")
    if he and he in registry["by_hebrew"]:
        return registry["by_hebrew"][he].get("english", "")
    return ""


def main():
    parser = argparse.ArgumentParser(description="Generate English translations for gallery photos.")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of photos per API request (default: 10)")
    parser.add_argument("--limit", type=int, default=0, help="Process up to N photos (0 for all)")
    parser.add_argument("--force", action="store_true", help="Force regenerate even if English fields exist")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY missing in environment or .env")
        sys.exit(1)

    registry = load_registry()
    print(f"Loaded species registry with {len(registry['by_latin'])} Latin & {len(registry['by_hebrew'])} Hebrew keys.")

    with open(PHOTOS_FILE, "r", encoding="utf-8") as f:
        photos = json.load(f)

    # שלב 1: הצמדת species_en לכל התמונות ישירות מהמאגר
    species_updated = 0
    for p in photos:
        ai = p.setdefault("ai", {})
        official_en = lookup_species_en(ai, registry)
        if official_en:
            ai["species_en"] = official_en
            species_updated += 1
        elif "species_en" not in ai:
            ai["species_en"] = ""

    print(f"Matched official species_en for {species_updated}/{len(photos)} photos from registry.")

    # שלב 2: סינון תמונות שצריכות תרגום
    to_process = []
    for idx, p in enumerate(photos):
        ai = p.get("ai", {})
        has_en = bool(ai.get("title_en") and ai.get("description_en"))
        if args.force or not has_en:
            to_process.append((idx, p))

    if args.limit > 0:
        to_process = to_process[:args.limit]

    print(f"Total photos to translate: {len(to_process)} (out of {len(photos)} total).")
    if not to_process:
        # שמירת עדכון ה-species_en אם בוצע
        with open(PHOTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(photos, f, ensure_ascii=False, indent=2)
        print("All photos already have English descriptions. Done!")
        return

    client = genai.Client(api_key=api_key)
    model_name = "gemini-3.1-flash-lite"

    batch_size = max(1, args.batch_size)
    total_batches = (len(to_process) + batch_size - 1) // batch_size
    processed_count = 0

    for b_idx in range(0, len(to_process), batch_size):
        chunk = to_process[b_idx:b_idx + batch_size]
        curr_batch = (b_idx // batch_size) + 1

        prompt_items = []
        for _, p in chunk:
            ai = p.get("ai", {})
            prompt_items.append({
                "id": p.get("id"),
                "title_he": ai.get("title", ""),
                "description_he": ai.get("description", ""),
                "humorous_description_he": ai.get("humorous_description", ""),
                "tags_he": ai.get("tags", []),
                "species_en": ai.get("species_en", ""),
                "category": ai.get("category", "wildlife"),
            })

        prompt = (
            "You are an expert bilingual wildlife and nature photography curator.\n"
            "Translate and adapt the following Israeli nature photos from Hebrew to English for an international photography portfolio:\n\n"
            "GUIDELINES:\n"
            "1. 'title_en': Evocative, engaging, and professional English title. If 'species_en' is provided, use the exact official English common name in the title when appropriate.\n"
            "2. 'description_en': A fluid, descriptive English sentence capturing the scene, lighting, action, and subject.\n"
            "3. 'humorous_description_en':\n"
            "   - CRITICAL RULE: If 'humorous_description_he' is EMPTY (\"\"), 'humorous_description_en' MUST be EMPTY (\"\")! Do not invent jokes where none exist.\n"
            "   - If 'humorous_description_he' has a funny caption, craft an equivalent witty, funny caption in natural English matching the spirit of the joke/photo.\n"
            "4. 'tags_en': 3-6 lowercase English tags (e.g. ['sunset', 'golden hour', 'red fox', 'wildlife']).\n\n"
            f"Input batch ({len(prompt_items)} photos):\n{json.dumps(prompt_items, ensure_ascii=False, indent=2)}"
        )

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BatchTranslationResponse,
                        temperature=0.2,
                    )
                )

                parsed: BatchTranslationResponse = response.parsed
                if parsed and parsed.translations:
                    trans_map = {t.id: t for t in parsed.translations}
                    for _, p in chunk:
                        pid = p.get("id")
                        if pid in trans_map:
                            t = trans_map[pid]
                            ai = p.setdefault("ai", {})
                            ai["title_en"] = sanitize_text(t.title_en)
                            ai["description_en"] = sanitize_text(t.description_en)
                            # וידוא כלל הברזל להומור
                            if not ai.get("humorous_description"):
                                ai["humorous_description_en"] = ""
                            else:
                                ai["humorous_description_en"] = sanitize_text(t.humorous_description_en)
                            ai["tags_en"] = [sanitize_text(tag).lower() for tag in t.tags_en if sanitize_text(tag)]

                    processed_count += len(chunk)
                    print(f"[{curr_batch}/{total_batches}] Successfully translated {len(chunk)} photos ({processed_count}/{len(to_process)} total).")
                    break
                else:
                    raise ValueError("Empty or unparsed translation response")

            except Exception as e:
                err_str = str(e)
                print(f"Batch {curr_batch} attempt {attempt} failed: {err_str[:120]}")
                if attempt < max_retries:
                    time.sleep(3.0 * attempt)
                else:
                    print(f"Skipping batch {curr_batch} after {max_retries} failed attempts.")

        # שמירת ביניים כל 5 אצוות (כ-50 תמונות) או בסיום
        if curr_batch % 5 == 0 or b_idx + batch_size >= len(to_process):
            with open(PHOTOS_FILE, "w", encoding="utf-8") as f:
                json.dump(photos, f, ensure_ascii=False, indent=2)
            print(f"Checkpoint saved to {PHOTOS_FILE} (completed {processed_count} photos).")

        time.sleep(0.5)

    print(f"Done! Successfully processed and saved translations for {processed_count} photos.")


if __name__ == "__main__":
    main()
