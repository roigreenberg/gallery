#!/usr/bin/env python3
"""
build_species_registry.py
=========================
מפיק מאגר שמות טקסונומי מקצועי ואחיד (species_registry.json)
עבור כל המינים הקיימים בגלריה באמצעות Gemini Flash וידע אורניתולוגי וזואולוגי רשמי.
"""

import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
PHOTOS_FILE = PROJECT_ROOT / "src" / "data" / "photos.json"
REGISTRY_FILE = PROJECT_ROOT / "src" / "data" / "species_registry.json"

class SpeciesEntry(BaseModel):
    key: str = Field(description="מפתח ייחודי - שם לטיני אם קיים, אחרת שם עברי תקני")
    latin: str = Field(default="", description="שם מדעי בלטינית (Binomial name)")
    hebrew: str = Field(description="שם עברי תקני רשמי (לפי האקדמיה/החברה להגנת הטבע)")
    english: str = Field(description="שם רשמי באנגלית (לפי IOC World Bird List / eBird / IUCN)")
    group: str = Field(description="קבוצה: birds, mammals, reptiles, amphibians, invertebrates, flora, landscapes, astronomy, other")
    aliases_he: list[str] = Field(default_factory=list, description="שמות נרדפים או וריאציות כתיב בעברית")

class SpeciesRegistryResponse(BaseModel):
    species: list[SpeciesEntry]

def extract_unique_species():
    with open(PHOTOS_FILE, "r", encoding="utf-8") as f:
        photos = json.load(f)

    from collections import defaultdict
    species_map = defaultdict(lambda: {"count": 0, "he": set(), "la": set(), "titles": set()})

    for p in photos:
        ai = p.get("ai", {})
        he = (ai.get("species_hebrew") or "").strip()
        la = (ai.get("species_latin") or "").strip()
        title = (ai.get("title") or "").strip()
        if he or la:
            key = la if la else he
            species_map[key]["count"] += 1
            if he: species_map[key]["he"].add(he)
            if la: species_map[key]["la"].add(la)
            if title and len(species_map[key]["titles"]) < 3:
                species_map[key]["titles"].add(title)

    items = []
    for k, v in sorted(species_map.items(), key=lambda x: -x[1]["count"]):
        items.append({
            "key": k,
            "count": v["count"],
            "hebrew": list(v["he"]),
            "latin": list(v["la"]),
            "sample_titles": list(v["titles"]),
        })
    return items

def main():
    items = extract_unique_species()
    print(f"Loaded {len(items)} unique species groups from photos.json.")

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY in environment or .env")

    client = genai.Client(api_key=api_key)

    # נחלק ל-2 פעימות של כ-120 פריטים כדי להבטיח דיוק מרבי ולמנוע חיתוך טוקנים
    chunk_size = 120
    all_registry_entries: list[SpeciesEntry] = []

    for chunk_idx in range(0, len(items), chunk_size):
        chunk = items[chunk_idx:chunk_idx + chunk_size]
        print(f"Processing chunk {chunk_idx // chunk_size + 1} ({len(chunk)} species)...")

        prompt = (
            "You are an expert wildlife biologist, ornithologist, and zoological taxonomist.\n"
            "Here is a list of nature photography species from an Israeli nature photographer's portfolio.\n"
            "For each item in the input, provide the standard, authoritative scientific taxonomy:\n"
            "1. 'key': keep the exact input key\n"
            "2. 'latin': the clean, correct binomial scientific Latin name (e.g., 'Athene noctua', 'Halcyon smyrnensis')\n"
            "3. 'hebrew': the standard canonical common Hebrew name used by the Israel Nature and Parks Authority and SPNI (e.g., 'כוס החורבות', 'שלדג לבן-חזה', 'שפן סלע')\n"
            "4. 'english': the official international English common name (e.g., IOC World Bird List for birds, e.g. 'Little Owl', 'White-throated Kingfisher', 'European Roller', 'Mountain Gazelle', 'Rock Hyrax'). DO NOT use literal translations!\n"
            "5. 'group': one of ['birds', 'mammals', 'reptiles', 'amphibians', 'invertebrates', 'flora', 'landscapes', 'astronomy', 'other']\n"
            "6. 'aliases_he': all Hebrew aliases seen in the input data\n\n"
            f"Input species list:\n{json.dumps(chunk, ensure_ascii=False, indent=2)}"
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SpeciesRegistryResponse,
                temperature=0.1,
            )
        )

        parsed: SpeciesRegistryResponse = response.parsed
        if parsed and parsed.species:
            print(f"Received {len(parsed.species)} species entries for chunk {chunk_idx // chunk_size + 1}.")
            all_registry_entries.extend(parsed.species)
        else:
            print("Warning: chunk returned empty or unparsed!")

    # שמירה ל-JSON מסודר
    registry_dict = {
        "_metadata": {
            "version": "1.0.0",
            "description": "Canonical species registry with official English & Hebrew names for Roi Greenberg Gallery",
            "total_species": len(all_registry_entries),
        },
        "by_latin": {},
        "by_hebrew": {},
        "entries": [entry.model_dump() for entry in all_registry_entries]
    }

    for entry in all_registry_entries:
        edata = entry.model_dump()
        if entry.latin:
            registry_dict["by_latin"][entry.latin.lower().strip()] = edata
        if entry.hebrew:
            registry_dict["by_hebrew"][entry.hebrew.strip()] = edata
        for alias in entry.aliases_he:
            registry_dict["by_hebrew"][alias.strip()] = edata

    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry_dict, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated species registry at {REGISTRY_FILE} with {len(all_registry_entries)} species entries!")

if __name__ == "__main__":
    main()
