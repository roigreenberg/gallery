import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
PHOTOS_FILE = PROJECT_ROOT / "src" / "data" / "photos.json"
REGISTRY_FILE = PROJECT_ROOT / "src" / "data" / "species_registry.json"

# Canonical mapping: latin (lowercase) -> (canonical_hebrew, canonical_english)
CANONICAL_MAP = {
    # 1. User specific request: חוגלת סלעים
    "alectoris chukar": ("חוגלת סלעים", "Chukar Partridge"),
    
    # 2. Main duplicates & variations
    "athene noctua": ("כוס החורבות", "Little Owl"),
    "procavia capensis": ("שפן סלע", "Rock Hyrax"),
    "gazella gazella": ("צבי ארצישראלי", "Mountain Gazelle"),
    "cinnyris osea": ("צופית בוהקת", "Palestine Sunbird"),
    "canis aureus": ("תן זהוב", "Golden Jackal"),
    "saxicola rubicola": ("דוחל שחור-גרון", "European Stonechat"),
    "saxicola rubetra": ("דוחל חום-גרון", "Whinchat"),
    "curruca melanocephala": ("סבכי שחור-ראש", "Sardinian Warbler"),
    "sylvia melanocephala": ("סבכי שחור-ראש", "Sardinian Warbler"),
    "merops orientalis": ("שרקרק גמדי", "Asian Green Bee-eater"),
    "coracias garrulus": ("כחל מצוי", "European Roller"),
    "grus grus": ("עגור אפור", "Common Crane"),
    "nycticorax nycticorax": ("אנפת לילה", "Black-crowned Night Heron"),
    "ceryle rudis": ("פרפור עקוד", "Pied Kingfisher"),
    "lanius collurio": ("חנקן אדום-גב", "Red-backed Shrike"),
    "bubulcus ibis": ("אנפית בקר", "Cattle Egret"),
    "erithacus rubecula": ("אדום-חזה", "European Robin"),
    "emberiza calandra": ("גיבתון עפרוני", "Corn Bunting"),
    "gallinula chloropus": ("סופית מצויה", "Common Moorhen"),
    "turdus merula": ("שחרור", "Common Blackbird"),
    "anas platyrhynchos": ("ברכייה", "Mallard"),
    "sylvia atricapilla": ("סבכי שחור-כיפה", "Eurasian Blackcap"),
    "garrulus glandarius": ("עורבני שחור-כיפה", "Eurasian Jay"),
    "chloris chloris": ("ירקון", "European Greenfinch"),
    "prinia gracilis": ("פשוש", "Graceful Prinia"),
    "argiope bruennichi": ("ארגיופ מצוי", "Wasp Spider"),
    "phylloscopus collybita": ("עלווית חורף", "Common Chiffchaff"),
    "parus major": ("ירגזי מצוי", "Great Tit"),
    "emberiza bruniceps": ("גיבתון אדום-ראש", "Red-headed Bunting"),
    "alopochen aegyptiaca": ("יאורית מצרית", "Egyptian Goose"),
    "ardeola ralloides": ("אנפית סוף", "Squacco Heron"),
    "apis mellifera": ("דבורת-דבש", "Western Honey Bee"),
    "himantopus himantopus": ("תמירון מצוי", "Black-winged Stilt"),
    "pastor roseus": ("זרזיר ורדרד", "Rosy Starling"),
    "anthus cervinus": ("פפיון אדום-גרון", "Red-throated Pipit"),
    "vitis vinifera": ("גפן", "Common Grape Vine"),
    "corvus monedula": ("קאק", "Western Jackdaw"),
    "galerida cristata": ("עפרוני מצויץ", "Crested Lark"),
    "papilio machaon": ("זנב-סנונית נאה", "Old World Swallowtail"),
    "carduelis carduelis": ("חוחית", "European Goldfinch"),
    "bubo bubo": ("אוח עיטי", "Eurasian Eagle-Owl"),
    "coccinella septempunctata": ("מושית השבע", "Seven-spot Ladybird"),
    "aporia crataegi": ("לבנין העוזרר", "Black-veined White"),
    "gallinago gallinago": ("חרטומית ביצות", "Common Snipe"),
    "mauremys caspica": ("צב ביצות מצוי", "Caspian Turtle"),
    "emys orbicularis": ("צב ביצות אירופי", "European Pond Turtle"),
    "psittacula krameri": ("דררה מצויה", "Rose-ringed Parakeet"),
    "otus scops": ("שעיר מצוי", "Common Scops Owl"),
    "linaria cannabina": ("תפוחית מצויה", "Common Linnet"),
    "sylvia curruca": ("סבכי טוחנים", "Lesser Whitethroat"),
    "luscinia megarhynchos": ("זמיר הירדן", "Common Nightingale"),
    "pandion haliaetus": ("שלך", "Western Osprey"),
    "jynx torquilla": ("סבראש", "Eurasian Wryneck"),
    "platalea leucorodia": ("כפן לבן", "Eurasian Spoonbill"),
    "sitta europaea": ("סיטה אירופית", "Eurasian Nuthatch"),
    "emberiza caesia": ("גיבתון אדום-מקור", "Cretzschmar's Bunting"),
    "emberiza cirlus": ("גיבתון גדרות", "Cirl Bunting"),
    "oenanthe leucopyga": ("סלעית לבנת-כנף", "White-crowned Wheatear"),
    "syrphidae": ("זבוב רחף", "Hoverfly"),
}

def clean_hebrew_text(text):
    if not text:
        return ""
    # Strip any stray foreign letters or characters
    t = re.sub(r"[^\u0590-\u05FF\s\-\(\)\'\"]", "", str(text))
    t = re.sub(r"\s+", " ", t).strip()
    return t

def update_registry():
    print(f"Loading registry from {REGISTRY_FILE}...")
    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        reg = json.load(f)

    entries = reg.get("entries", [])
    updated_entries = 0

    for entry in entries:
        la = entry.get("latin", "").strip().lower()
        if la in CANONICAL_MAP:
            new_he, new_en = CANONICAL_MAP[la]
            old_he = entry.get("hebrew")
            old_en = entry.get("english")
            if old_he != new_he or old_en != new_en:
                entry["hebrew"] = new_he
                entry["english"] = new_en
                # ensure old Hebrew is in aliases
                if old_he and old_he not in entry.get("aliases_he", []):
                    entry.setdefault("aliases_he", []).append(old_he)
                updated_entries += 1

    # Rebuild by_latin and by_hebrew
    by_latin = {}
    by_hebrew = {}
    for entry in entries:
        la = entry.get("latin", "").strip().lower()
        he = entry.get("hebrew", "").strip()
        if la:
            by_latin[la] = entry
        if he:
            by_hebrew[he] = entry
        for alias in entry.get("aliases_he", []):
            al = alias.strip()
            if al and al not in by_hebrew:
                by_hebrew[al] = entry

    reg["entries"] = entries
    reg["by_latin"] = by_latin
    reg["by_hebrew"] = by_hebrew

    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)

    print(f"Registry updated: {updated_entries} entries updated with canonical names.")

def update_photos():
    print(f"Loading photos from {PHOTOS_FILE}...")
    with open(PHOTOS_FILE, "r", encoding="utf-8") as f:
        photos = json.load(f)

    species_he_changes = 0
    title_chukar_changes = 0

    for p in photos:
        ai = p.get("ai", {})
        la = (ai.get("species_latin") or "").strip().lower()
        old_he = (ai.get("species_hebrew") or "").strip()
        
        # 1. Update species_hebrew and species_en if in CANONICAL_MAP
        if la in CANONICAL_MAP:
            canon_he, canon_en = CANONICAL_MAP[la]
            if old_he != canon_he:
                ai["species_hebrew"] = canon_he
                species_he_changes += 1
            if ai.get("species_en") != canon_en:
                ai["species_en"] = canon_en

        # 2. Check standalone 'חוגלה' / 'חוגלה' variations in Hebrew
        if "חוגל" in old_he and la not in CANONICAL_MAP:
            ai["species_hebrew"] = "חוגלת סלעים"
            ai["species_latin"] = "Alectoris chukar"
            ai["species_en"] = "Chukar Partridge"
            species_he_changes += 1

        # 3. Clean any stray weird characters in species_hebrew
        current_he = ai.get("species_hebrew", "")
        cleaned_he = clean_hebrew_text(current_he)
        if current_he != cleaned_he:
            ai["species_hebrew"] = cleaned_he
            species_he_changes += 1

        # 4. Check photo title and description for chukar and weird characters
        title = ai.get("title", "")
        desc = ai.get("description", "")
        
        # Explicit fixes for specific IDs if needed
        explicit_title_fixes = {
            "20260412-RG5_7156_1": "חוגלת סלעים עומדת על מבנה גבוה",
            "20260412-RG5_7067_1": "חוגלת סלעים עומדת על סלע באור ראשון",
            "20260412-RG5_7042": "חוגלת סלעים על סלע בטבע",
            "20260412-RG5_7031": "חוגלת סלעים עומדת על סלע באור זהוב",
            "20260412-RG5_0033": "שלך במעוף מעל המים",
        }
        
        pid = p.get("id")
        if pid in explicit_title_fixes:
            ai["title"] = explicit_title_fixes[pid]
            title_chukar_changes += 1
            new_title = explicit_title_fixes[pid]
        else:
            new_title = title
            # If title still has standalone "חוגלה" or "חוגה"
            for old_w in ["חוגלה סלעים", "חוגלה האבן", "חוגלת האבן", "חוגלה", "חוגة"]:
                if old_w in new_title:
                    new_title = new_title.replace(old_w, "חוגלת סלעים")
            if new_title != title:
                ai["title"] = new_title
                title_chukar_changes += 1

        replacements = [
            ("חוגלה סלעים", "חוגלת סלעים"),
            ("חוגלה האבן", "חוגלת סלעים"),
            ("חוגלת האבן", "חוגלת סלעים"),
            ("חוגלה", "חוגלת סלעים"),
            ("שלת אלעזרי", "שלך"),
            ("עגur אפור", "עגור אפור"),
            ("עגור אפור", "עגור אפור"),
            ("פסיخان עדין", "פשוש"),
            ("אנפית סופסוף", "אנפית סוף"),
            ("זובוב רחף", "זבוב רחף"),
            ("תאן זהוב", "תן זהוב"),
            ("סופנית מצויה", "סופית מצויה"),
        ]

        new_desc = desc
        new_desc = new_desc.replace("חוגל\u0629", "חוגלת")
        for old_s, new_s in replacements:
            if old_s in new_desc:
                new_desc = new_desc.replace(old_s, new_s)
        if new_desc != desc:
            ai["description"] = new_desc

    with open(PHOTOS_FILE, "w", encoding="utf-8") as f:
        json.dump(photos, f, ensure_ascii=False, indent=2)

    print(f"Photos updated: {species_he_changes} species_hebrew updates, {title_chukar_changes} chukar title updates.")

if __name__ == "__main__":
    update_registry()
    update_photos()
    print("Standardization complete!")
