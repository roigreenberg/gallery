#!/usr/bin/env python3
"""
process_photos.py
=================
סקריפט שלם ומודולרי לעיבוד תמונות גלריה:
1. סריקה ועיבוד אינקרמנטלי מתיקיית מקור מקומית.
2. אופטימיזציה וכיווץ (Pillow):
   - תמונות תצוגה (Display): המרה ל-WebP איכותי (Quality 100) ללא שינוי רזולוציה.
   - תמונות ממוזערות (Thumbnails): עד רוחב 500px, שמירה כ-WebP (Quality 80).
   - סיבוב תמונה אוטומטי (EXIF Transpose).
3. חילוץ מלא של נתוני EXIF (דגם מצלמה, דגם עדשה, אורך מוקד, צמצם, זמן חשיפה, אסא, תאריך).
4. תיוג AI חכם באמצעות Gemini Flash API (google-genai SDK) עם Structured JSON Output.
5. שמירה מרוכזת ורציפה לתוך ./src/data/photos.json והצגת התקדמות ב-tqdm.
"""

from __future__ import annotations

import warnings
# השתקת אזהרות עתידיות של ספריות צד-שלישי בסביבות ישנות
warnings.filterwarnings("ignore", category=FutureWarning)

import argparse
import fractions
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# תמיכה בהדפסת עברית ואימוג'ים בטרמינל Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# טעינת משתני סביבה (למשל מתוך קובץ .env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from PIL import Image, ImageOps, ExifTags
from tqdm import tqdm
from pydantic import BaseModel, Field, ConfigDict

# ספריית exifread כגיבוי לחילוץ EXIF
try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False

# ספריית boto3 עבור Cloudflare R2 / S3
try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

# ספריית Google GenAI הרשמית
try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    HAS_GOOGLE_GENAI = True
except ImportError:
    HAS_GOOGLE_GENAI = False


# ==============================================================================
# הגדרות תצורה ראשיות (Configuration & Paths)
# ==============================================================================

# נתיב ברירת מחדל לתיקיית המקור (ניתן לשינוי גם דרך דגל --source בהרצה)
DEFAULT_SOURCE_DIR: str = r"C:\Users\Roi\Pictures\תמונות לאתר"

# נתיבי פלט לפרויקט
PROJECT_ROOT: Path = Path(__file__).resolve().parent
DEFAULT_DISPLAY_DIR: Path = PROJECT_ROOT / "public" / "photos" / "display"
DEFAULT_THUMBS_DIR: Path = PROJECT_ROOT / "public" / "photos" / "thumbs"
DEFAULT_DATA_FILE: Path = PROJECT_ROOT / "src" / "data" / "photos.json"
DEFAULT_SPECIES_REGISTRY_FILE: Path = PROJECT_ROOT / "src" / "data" / "species_registry.json"

# סיומות קבצים נתמכות
SUPPORTED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# פרמטרי אופטימיזציה לתמונות
DISPLAY_QUALITY: int = 100       # איכות WebP מקסימלית לתמונת תצוגה
THUMB_QUALITY: int = 80          # איכות WebP עבור Thumbnail
THUMB_MAX_WIDTH: int = 500       # רוחב מרבי לתמונה ממוזערת
DEFAULT_BATCH_SIZE: int = 5      # מספר תמונות שנשלחות יחד בבקשת AI אחת

# הגדרות מודל ה-AI - מודל קל ומהיר עם מכסה יומית ייעודית
DEFAULT_GEMINI_MODEL: str = "gemini-3.1-flash-lite"

# הגדרת לוגר
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("process_photos")


# ==============================================================================
# מודלים של נתונים (Pydantic Models)
# ==============================================================================

class PhotoAITags(BaseModel):
    """מבנה פלט מובנה (Structured JSON) מתיוג ה-AI של Gemini Flash."""
    title: str = Field(
        default="",
        description="כותרת קצרה וקולעת בעברית המתארת את התמונה"
    )
    species_hebrew: Optional[str] = Field(
        default="",
        description="שם המין המדויק בעברית (אם יש בעל חיים, ציפור, צמח, חרק או גרם שמיים, אחרת מחרוזת ריקה)"
    )
    species_latin: Optional[str] = Field(
        default="",
        description="שם מדעי בלטינית (אם רלוונטי, אחרת מחרוזת ריקה)"
    )
    category: str = Field(
        default="wildlife",
        description="קטגוריה ראשית מתוך: wildlife, landscape, astrophotography, macro, portrait, other"
    )
    behavior: List[str] = Field(
        default_factory=list,
        description="רשימת התנהגויות ייחודיות הנראות בתמונה (למשל: ['מעוף', 'ציד', 'צלילה', 'מנוחה'])"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="3-6 תגיות רלוונטיות בעברית לסינון וחיפוש בגלריה"
    )
    description: str = Field(
        default="",
        description="תיאור קצר במשפט אחד בעברית המעביר את הסיפור של התמונה"
    )
    humorous_description: Optional[str] = Field(
        default=None,
        description="תיאור קצר, משעשע ומבדר במשפט אחד בעברית רק אם הסיטואציה/ההבעה בתמונה מצחיקה באופן טבעי, אחרת מחרוזת ריקה"
    )
    species_en: Optional[str] = Field(
        default="",
        description="שם המין הרשמי באנגלית (Standard international English common name)"
    )
    title_en: Optional[str] = Field(
        default="",
        description="כותרת קצרה, מרשימה וקולעת באנגלית"
    )
    description_en: Optional[str] = Field(
        default="",
        description="תיאור קצר במשפט אחד באנגלית"
    )
    humorous_description_en: Optional[str] = Field(
        default="",
        description="תיאור משעשע ושנון באנגלית רק אם יש תיאור הומוריסטי בעברית, אחרת מחרוזת ריקה"
    )
    tags_en: List[str] = Field(
        default_factory=list,
        description="3-6 תגיות רלוונטיות באנגלית לסינון וחיפוש"
    )


class BatchItemAITags(BaseModel):
    """פריט בודד בתוך תשובת Batch."""
    index: int = Field(description="מספר התמונה ברשימה (1, 2, ...)")
    title: str = Field(default="", description="כותרת קצרה וקולעת בעברית")
    species_hebrew: Optional[str] = Field(default="", description="שם המין המדויק בעברית")
    species_latin: Optional[str] = Field(default="", description="שם מדעי בלטינית")
    species_en: Optional[str] = Field(default="", description="שם רשמי באנגלית")
    category: str = Field(default="wildlife", description="קטגוריה ראשית")
    behavior: List[str] = Field(default_factory=list, description="התנהגויות")
    tags: List[str] = Field(default_factory=list, description="3-6 תגיות בעברית")
    description: str = Field(default="", description="תיאור קצר במשפט אחד בעברית")
    humorous_description: Optional[str] = Field(
        default="",
        description="תיאור קצר ומבדר במשפט אחד בעברית רק אם יש הומור אותנטי, אחרת מחרוזת ריקה"
    )
    title_en: Optional[str] = Field(default="", description="כותרת באנגלית")
    description_en: Optional[str] = Field(default="", description="תיאור באנגלית")
    humorous_description_en: Optional[str] = Field(default="", description="תיאור הומוריסטי באנגלית רק אם יש הומור בעברית")
    tags_en: List[str] = Field(default_factory=list, description="תגיות באנגלית")


class BatchPhotosAITags(BaseModel):
    """תשובה מרוכזת מקריאת Batch ל-Gemini."""
    items: List[BatchItemAITags] = Field(default_factory=list)


class BatchHumorItem(BaseModel):
    """פריט בודד של תיאור הומוריסטי מקריאת Batch."""
    index: int = Field(description="מספר התמונה ברשימה (1, 2, ...)")
    humorous_description: Optional[str] = Field(
        default="",
        description="תיאור קצר, משעשע ומבדר במשפט אחד בעברית רק אם הסיטואציה משעשעת באופן טבעי, אחרת מחרוזת ריקה"
    )


class BatchHumorResponse(BaseModel):
    """תשובת Batch לתיוג הומוריסטי בלבד."""
    items: List[BatchHumorItem] = Field(default_factory=list)


class ExifMetadata(BaseModel):
    """נתוני צילום טכניים שחולצו מ-EXIF."""
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    focal_length: Optional[str] = None
    aperture: Optional[str] = None
    shutter_speed: Optional[str] = None
    iso: Optional[int] = None
    date_time_original: Optional[str] = None


class Dimensions(BaseModel):
    """ממדי תמונת התצוגה."""
    width: int
    height: int
    aspect_ratio: float


class RelativePaths(BaseModel):
    """נתיבים לקובצי המדיה ברשת (מקומיים או מלאים)."""
    display: str
    thumbnail: str


class PhotoRecord(BaseModel):
    """רשומת תמונה מלאה עבור photos.json."""
    model_config = ConfigDict(extra="allow")

    id: str
    filename: str
    original_filename: str
    display_url: Optional[str] = None
    thumb_url: Optional[str] = None
    paths: RelativePaths
    dimensions: Dimensions
    exif: ExifMetadata
    ai: PhotoAITags
    processed_at: str
    last_edited_at: Optional[str] = None
    is_featured: Optional[bool] = False


# ==============================================================================
# חילוץ ועיבוד נתוני EXIF
# ==============================================================================

def format_shutter_speed(val: Any) -> Optional[str]:
    """
    המרה של זמן חשיפה לשבר קריא (למשל 1/1000s, 1/100s) או שניות שלמות (2s).
    """
    if val is None:
        return None
    try:
        if isinstance(val, (tuple, list)) and len(val) == 2:
            num, denom = val
            if denom == 0:
                return None
            val = float(num) / float(denom)
        elif isinstance(val, fractions.Fraction):
            val = float(val)
        else:
            val = float(val)

        if val <= 0:
            return None
        if val >= 1.0:
            return f"{int(val)}s" if val.is_integer() else f"{val:.1f}s"
        
        reciprocal = round(1.0 / val)
        return f"1/{reciprocal}s"
    except Exception:
        return str(val) if val else None


def format_aperture(val: Any) -> Optional[str]:
    """
    עיצוב ערך צמצם בפורמט f/X.X (לדוגמה f/2.8, f/8).
    """
    if val is None:
        return None
    try:
        if isinstance(val, (tuple, list)) and len(val) == 2:
            num, denom = val
            if denom == 0:
                return None
            fval = float(num) / float(denom)
        else:
            fval = float(val)
        
        if fval.is_integer():
            return f"f/{int(fval)}"
        return f"f/{fval:.1f}"
    except Exception:
        return f"f/{val}" if val else None


def format_focal_length(val: Any) -> Optional[str]:
    """
    עיצוב אורך מוקד כולל יחידת מידה mm (לדוגמה 100mm, 500mm).
    """
    if val is None:
        return None
    try:
        if isinstance(val, (tuple, list)) and len(val) == 2:
            num, denom = val
            if denom == 0:
                return None
            fval = float(num) / float(denom)
        else:
            fval = float(val)
        
        if fval.is_integer():
            return f"{int(fval)}mm"
        return f"{fval:.1f}mm"
    except Exception:
        return f"{val}mm" if val else None


def format_camera_model(make: Optional[str], model: Optional[str]) -> Optional[str]:
    """איחוד יצרן ודגם למחרוזת נקייה ללא כפילויות (למשל 'Canon EOS R7')."""
    if not model and not make:
        return None
    model_str = str(model or "").strip()
    make_str = str(make or "").strip()

    if not make_str:
        return model_str
    if not model_str:
        return make_str
    
    # אם שם היצרן כבר מופיע בדגם (למשל Canon בתוך Canon EOS R7), נשאיר רק את הדגם
    if make_str.lower() in model_str.lower():
        return model_str
    return f"{make_str} {model_str}"


def extract_exif(image_path: Path, pil_image: Image.Image) -> ExifMetadata:
    """
    חילוץ נתוני EXIF מלאים מתמונה באמצעות Pillow, עם גיבוי exifread בעת הצורך.
    """
    camera_model = None
    lens_model = None
    focal_length = None
    aperture = None
    shutter_speed = None
    iso = None
    date_time_original = None

    # שיטה 1: Pillow getexif() ו-IFD תת-רמות
    try:
        raw_exif = pil_image.getexif()
        if raw_exif:
            # נתונים מ-IFD ראשי (0)
            make = raw_exif.get(0x010F)    # Make
            model = raw_exif.get(0x0110)   # Model
            camera_model = format_camera_model(make, model)

            # נתונים מ-Exif SubIFD (0x8769)
            sub_ifd = raw_exif.get_ifd(0x8769) or {}

            # עדשה
            lens_model = sub_ifd.get(0xA434) or raw_exif.get(0xA434)
            if lens_model:
                lens_model = str(lens_model).strip()

            # אורך מוקד
            raw_focal = sub_ifd.get(0x920A) or raw_exif.get(0x920A)
            focal_length = format_focal_length(raw_focal)

            # צמצם
            raw_fnum = sub_ifd.get(0x829D) or raw_exif.get(0x829D) or sub_ifd.get(0x9202)
            aperture = format_aperture(raw_fnum)

            # זמן חשיפה
            raw_exp = sub_ifd.get(0x829A) or raw_exif.get(0x829A)
            shutter_speed = format_shutter_speed(raw_exp)

            # ISO
            raw_iso = sub_ifd.get(0x8827) or raw_exif.get(0x8827)
            if raw_iso is not None:
                try:
                    iso = int(raw_iso)
                except (ValueError, TypeError):
                    iso = None

            # תאריך ושעה מקוריים
            raw_date = sub_ifd.get(0x9003) or sub_ifd.get(0x9004) or raw_exif.get(0x0132)
            if raw_date:
                date_time_original = str(raw_date).strip()
    except Exception as e:
        logger.debug(f"Pillow EXIF extraction warning on {image_path.name}: {e}")

    # שיטה 2: גיבוי באמצעות exifread אם חסרים שדות מרכזיים
    if HAS_EXIFREAD and (not lens_model or not shutter_speed or not aperture or not camera_model):
        try:
            with open(image_path, "rb") as f:
                tags = exifread.process_file(f, details=False)
                
                if not camera_model:
                    make_tag = tags.get("Image Make")
                    model_tag = tags.get("Image Model")
                    camera_model = format_camera_model(
                        str(make_tag) if make_tag else None,
                        str(model_tag) if model_tag else None
                    )

                if not lens_model:
                    for l_key in ("EXIF LensModel", "Image LensModel", "EXIF LensType"):
                        if l_key in tags:
                            lens_model = str(tags[l_key]).strip()
                            break

                if not focal_length and "EXIF FocalLength" in tags:
                    focal_length = format_focal_length(tags["EXIF FocalLength"].values)

                if not aperture and "EXIF FNumber" in tags:
                    aperture = format_aperture(tags["EXIF FNumber"].values)

                if not shutter_speed and "EXIF ExposureTime" in tags:
                    shutter_speed = format_shutter_speed(tags["EXIF ExposureTime"].values)

                if iso is None and "EXIF ISOSpeedRatings" in tags:
                    try:
                        iso = int(str(tags["EXIF ISOSpeedRatings"]))
                    except (ValueError, TypeError):
                        pass

                if not date_time_original:
                    for d_key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
                        if d_key in tags:
                            date_time_original = str(tags[d_key]).strip()
                            break
        except Exception as e:
            logger.debug(f"exifread fallback warning on {image_path.name}: {e}")

    return ExifMetadata(
        camera_model=camera_model,
        lens_model=lens_model,
        focal_length=focal_length,
        aperture=aperture,
        shutter_speed=shutter_speed,
        iso=iso,
        date_time_original=date_time_original,
    )


def sanitize_text(text: Optional[str]) -> str:
    """ניקוי מחרוזות מתווי בקרה, סימני bidi, גרשיים ומרכאות עודפות ורווחים כפולים."""
    if not text:
        return ""
    t = re.sub(r"[\u200e\u200f\u202a-\u202e\ufeff\u200b\ufffd]", "", str(text))
    t = re.sub(r"^[\"\'\`\*\_\#\s]+|[\"\'\`\*\_\#\s]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ==============================================================================
# תיוג תמונה באמצעות Gemini Flash API
# ==============================================================================

class AITagger:
    """מחלקת תיוג תמונות מבוססת Gemini Flash API דרך google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model_name = model_name
        self.client: Optional[genai.Client] = None
        self._available = False

        self.species_registry: Dict[str, dict] = self._load_registry()

        if not HAS_GOOGLE_GENAI:
            logger.warning("החבילה 'google-genai' אינה מותקנת. תיוג ה-AI יוחלף בברירות מחדל.")
            return

        if not self.api_key:
            logger.warning("משתנה GEMINI_API_KEY אינו מוגדר. תיוג ה-AI יוחלף בברירות מחדל.")
            return

        try:
            self.client = genai.Client(api_key=self.api_key)
            self._available = True
            logger.info(f"Gemini API מאותחל בהצלחה (מודל: {self.model_name}).")
        except Exception as e:
            logger.warning(f"שגיאה באתחול Gemini Client: {e}")

    def _load_registry(self) -> Dict[str, dict]:
        """טעינת מאגר השמות הטקסונומי הרשמי species_registry.json."""
        if not DEFAULT_SPECIES_REGISTRY_FILE.exists():
            return {"by_latin": {}, "by_hebrew": {}}
        try:
            with open(DEFAULT_SPECIES_REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "by_latin": {k.lower().strip(): v for k, v in data.get("by_latin", {}).items()},
                "by_hebrew": {k.strip(): v for k, v in data.get("by_hebrew", {}).items()},
            }
        except Exception as e:
            logger.warning(f"שגיאה בטעינת מאגר השמות: {e}")
            return {"by_latin": {}, "by_hebrew": {}}

    def _resolve_species_en(self, species_latin: Optional[str], species_hebrew: Optional[str]) -> str:
        """שליפת שם המין הרשמי באנגלית ממאגר השמות."""
        la = (species_latin or "").strip().lower()
        he = (species_hebrew or "").strip()
        if la and la in self.species_registry.get("by_latin", {}):
            return self.species_registry["by_latin"][la].get("english", "")
        if he and he in self.species_registry.get("by_hebrew", {}):
            return self.species_registry["by_hebrew"][he].get("english", "")
        return ""

    @property
    def is_available(self) -> bool:
        return self._available

    def tag_image(self, thumb_image: Image.Image, filename: str) -> PhotoAITags:
        """
        שליחת תמונת ה-Thumbnail ל-Gemini Flash API לקבלת תיוג מובנה בעברית.
        כולל מנגנון Retry ועמידות בפני שגיאות.
        """
        if not self.is_available or self.client is None:
            return self._fallback_tags(filename)

        # המרת ה-Thumbnail לבייטים של WebP
        thumb_buffer = io.BytesIO()
        thumb_image.save(thumb_buffer, format="WEBP", quality=80)
        image_bytes = thumb_buffer.getvalue()

        prompt = (
            "אתה מומחה לצילום טבע, צפרות, חיות בר, צילום נוף ומאקרו.\n"
            "נתח את התמונה המצורפת וחלץ פרטים מדויקים בעברית ובאנגלית עבור גלריית צילום מקצועית:\n"
            "1. title: כותרת קצרה, מרשימה וקולעת בעברית.\n"
            "2. title_en: Evocative, engaging, and professional English title.\n"
            "3. species_hebrew: שם המין המדויק בעברית (אם יש בעל חיים/צמח/גרם שמיים, אחרת מחרוזת ריקה).\n"
            "4. species_latin: שם מדעי רשמי בלטינית (Binomial name, למשל 'Halcyon smyrnensis').\n"
            "5. species_en: Official English common name (e.g. 'White-throated Kingfisher', 'Rock Hyrax').\n"
            "6. category: wildlife, landscape, astrophotography, macro, portrait, urban, nature.\n"
            "7. behavior: רשימת התנהגויות ייחודיות הנראות בתמונה.\n"
            "8. tags: 3 עד 6 תגיות רלוונטיות בעברית לסינון בגלריה.\n"
            "9. tags_en: 3 to 6 relevant lowercase English tags.\n"
            "10. description: תיאור קצר, מדויק ופואטי במשפט אחד בעברית.\n"
            "11. description_en: Descriptive, atmospheric English sentence capturing the scene and lighting.\n"
            "12. humorous_description: תיאור קצר, משעשע ומבדר במשפט אחד בעברית רק אם הסיטואציה/ההבעה בתמונה מצחיקה באופן טבעי (למשל מחשבות פנימיות של החיה, כיתוב שנון). אם אין משהו משעשע באופן אותנטי, השאר מחרוזת ריקה (\"\") - לא בכוח!\n"
            "13. humorous_description_en: Witty English caption ONLY if humorous_description exists. If no humor, MUST be empty (\"\")!\n"
            "החזר פלט מובנה התואם ל-Schema."
        )

        max_retries = 2
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PhotoAITags,
                    temperature=0.2,
                )

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_bytes, mime_type="image/webp"),
                    ],
                    config=config,
                )

                if response.parsed and isinstance(response.parsed, PhotoAITags):
                    p = response.parsed
                    sp_he = sanitize_text(p.species_hebrew)
                    sp_la = sanitize_text(p.species_latin)
                    sp_en = self._resolve_species_en(sp_la, sp_he) or sanitize_text(p.species_en)
                    h_he = sanitize_text(p.humorous_description)
                    h_en = sanitize_text(p.humorous_description_en) if h_he else ""
                    return PhotoAITags(
                        title=sanitize_text(p.title),
                        title_en=sanitize_text(p.title_en),
                        species_hebrew=sp_he,
                        species_latin=sp_la,
                        species_en=sp_en,
                        category=sanitize_text(p.category) or "wildlife",
                        behavior=[sanitize_text(b) for b in p.behavior if sanitize_text(b)],
                        tags=[sanitize_text(t) for t in p.tags if sanitize_text(t)] or ["טבע"],
                        tags_en=[sanitize_text(t).lower() for t in (p.tags_en or []) if sanitize_text(t)],
                        description=sanitize_text(p.description),
                        description_en=sanitize_text(p.description_en),
                        humorous_description=h_he,
                        humorous_description_en=h_en,
                    )

                # גיבוי ניתוח JSON ידני
                raw_text = response.text or "{}"
                data = json.loads(raw_text)
                sp_he = sanitize_text(data.get("species_hebrew"))
                sp_la = sanitize_text(data.get("species_latin"))
                sp_en = self._resolve_species_en(sp_la, sp_he) or sanitize_text(data.get("species_en"))
                h_he = sanitize_text(data.get("humorous_description"))
                h_en = sanitize_text(data.get("humorous_description_en")) if h_he else ""
                return PhotoAITags(
                    title=sanitize_text(data.get("title")),
                    title_en=sanitize_text(data.get("title_en")),
                    species_hebrew=sp_he,
                    species_latin=sp_la,
                    species_en=sp_en,
                    category=sanitize_text(data.get("category")) or "wildlife",
                    behavior=[sanitize_text(b) for b in data.get("behavior", []) if sanitize_text(b)],
                    tags=[sanitize_text(t) for t in data.get("tags", ["טבע"]) if sanitize_text(t)] or ["טבע"],
                    tags_en=[sanitize_text(t).lower() for t in data.get("tags_en", []) if sanitize_text(t)],
                    description=sanitize_text(data.get("description")),
                    description_en=sanitize_text(data.get("description_en")),
                    humorous_description=h_he,
                    humorous_description_en=h_en,
                )

            except Exception as e:
                err_str = str(e)
                if attempt < max_retries:
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        time.sleep(4.0)
                    else:
                        time.sleep(2.0)
                else:
                    logger.warning(f"דילוג על תיוג AI עבור '{filename}' עקב מגבלת קצב/שגיאה: שימוש בברירות מחדל.")
                    return self._fallback_tags(filename)

        return self._fallback_tags(filename)

    def tag_batch(self, items: List[Tuple[Image.Image, str]]) -> List[PhotoAITags]:
        """
        שליחת מקבץ תמונות (Batch) בבקשת AI אחת, לחסכון עצום בקריאות ובזמן.
        """
        if not self.is_available or self.client is None or not items:
            return [self._fallback_tags(fn) for _, fn in items]

        if len(items) == 1:
            return [self.tag_image(items[0][0], items[0][1])]

        contents = [
            "אתה מומחה בינלאומי לצילום טבע, צפרות, חיות בר, צילום נוף ומאקרו.\n"
            "לפניך קבוצה של מספר תמונות ממוספרות (תמונה 1, תמונה 2, וכו').\n"
            "נתח כל תמונה בנפרד וחלץ פרטים בעברית ובאנגלית עבור כל אינדקס (index) בהתאמה:\n"
            "- index: מספר התמונה (1, 2, ...)\n"
            "- title: כותרת קצרה וקולעת בעברית (ללא מרכאות)\n"
            "- title_en: Evocative, professional English title\n"
            "- species_hebrew: שם המין המדויק בעברית (אם יש בעל חיים/צמח/גרם שמיים, אחרת מחרוזת ריקה)\n"
            "- species_latin: שם מדעי רשמי בלטינית (Binomial name, למשל 'Halcyon smyrnensis')\n"
            "- species_en: Official English common name (e.g. 'White-throated Kingfisher', 'Rock Hyrax')\n"
            "- category: קטגוריה ראשית (wildlife, landscape, macro, astrophotography, portrait, urban, nature)\n"
            "- behavior: רשימת התנהגויות ייחודיות הנראות בתמונה\n"
            "- tags: 3 עד 6 תגיות רלוונטיות בעברית לסינון\n"
            "- tags_en: 3 to 6 relevant lowercase English tags\n"
            "- description: תיאור קצר במשפט אחד בעברית\n"
            "- description_en: Descriptive, atmospheric English sentence\n"
            "- humorous_description: תיאור קצר ומשעשע בעברית רק אם הסיטואציה/ההבעה בתמונה מצחיקה באופן טבעי, אחרת מחרוזת ריקה (\"\") - לא בכוח!\n"
            "- humorous_description_en: Witty English caption ONLY if humorous_description exists, else empty (\"\")!\n"
        ]

        for idx, (thumb_img, fn) in enumerate(items, 1):
            contents.append(f"תמונה {idx} (שם קובץ: {fn}):")
            buf = io.BytesIO()
            thumb_img.save(buf, format="WEBP", quality=80)
            contents.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/webp"))

        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                cfg = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BatchPhotosAITags,
                    temperature=0.2,
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=cfg,
                )

                parsed_map = {}
                if response.parsed and isinstance(response.parsed, BatchPhotosAITags):
                    for p in response.parsed.items:
                        sp_he = sanitize_text(p.species_hebrew)
                        sp_la = sanitize_text(p.species_latin)
                        sp_en = self._resolve_species_en(sp_la, sp_he) or sanitize_text(p.species_en)
                        h_he = sanitize_text(p.humorous_description)
                        h_en = sanitize_text(p.humorous_description_en) if h_he else ""
                        parsed_map[p.index] = PhotoAITags(
                            title=sanitize_text(p.title),
                            title_en=sanitize_text(p.title_en),
                            species_hebrew=sp_he,
                            species_latin=sp_la,
                            species_en=sp_en,
                            category=sanitize_text(p.category) or "wildlife",
                            behavior=[sanitize_text(b) for b in (p.behavior or []) if sanitize_text(b)],
                            tags=[sanitize_text(t) for t in (p.tags or ["טבע"]) if sanitize_text(t)] or ["טבע"],
                            tags_en=[sanitize_text(t).lower() for t in (p.tags_en or []) if sanitize_text(t)],
                            description=sanitize_text(p.description),
                            description_en=sanitize_text(p.description_en),
                            humorous_description=h_he,
                            humorous_description_en=h_en,
                        )
                elif response.text:
                    raw_data = json.loads(response.text)
                    raw_items = raw_data.get("items", []) if isinstance(raw_data, dict) else raw_data
                    for p in raw_items:
                        idx = p.get("index", len(parsed_map) + 1)
                        sp_he = sanitize_text(p.get("species_hebrew"))
                        sp_la = sanitize_text(p.get("species_latin"))
                        sp_en = self._resolve_species_en(sp_la, sp_he) or sanitize_text(p.get("species_en"))
                        h_he = sanitize_text(p.get("humorous_description"))
                        h_en = sanitize_text(p.get("humorous_description_en")) if h_he else ""
                        parsed_map[idx] = PhotoAITags(
                            title=sanitize_text(p.get("title")),
                            title_en=sanitize_text(p.get("title_en")),
                            species_hebrew=sp_he,
                            species_latin=sp_la,
                            species_en=sp_en,
                            category=sanitize_text(p.get("category")) or "wildlife",
                            behavior=[sanitize_text(b) for b in p.get("behavior", []) if sanitize_text(b)],
                            tags=[sanitize_text(t) for t in p.get("tags", ["טבע"]) if sanitize_text(t)] or ["טבע"],
                            tags_en=[sanitize_text(t).lower() for t in p.get("tags_en", []) if sanitize_text(t)],
                            description=sanitize_text(p.get("description")),
                            description_en=sanitize_text(p.get("description_en")),
                            humorous_description=h_he,
                            humorous_description_en=h_en,
                        )

                results = []
                for idx, (_, fn) in enumerate(items, 1):
                    if idx in parsed_map and parsed_map[idx].title:
                        results.append(parsed_map[idx])
                    else:
                        results.append(self._fallback_tags(fn))

                time.sleep(1.0)
                return results

            except Exception as e:
                err_str = str(e)
                if attempt < max_retries:
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        time.sleep(5.0)
                    else:
                        time.sleep(2.0)
                else:
                    logger.warning("דילוג על תיוג Batch עקב שגיאה: שימוש בברירות מחדל.")
                    return [self._fallback_tags(fn) for _, fn in items]

        return [self._fallback_tags(fn) for _, fn in items]

    def tag_humor_batch(
        self,
        items: List[Tuple[Image.Image, str, str]]
    ) -> List[str]:
        """
        שליחת מקבץ (Batch) של תמונות קיימות לקבלת תיאור הומוריסטי/משעשע בלבד.
        """
        if not self.is_available or self.client is None or not items:
            return ["" for _ in items]

        contents = [
            "אתה מומחה לצילום טבע עם חוש הומור חד, שנון, משובח ומצחיק.\n"
            f"לפניך קבוצה של {len(items)} תמונות טבע. עבור כל תמונה (לפי מספר ה-index שלה),\n"
            "בדוק היטב את התמונה, הבעת הפנים, התנוחה או הרגע:\n"
            "1. אם יש בסיטואציה משהו קומי, משעשע או מבדר (למשל: מחשבות פנימיות של החיה, הבעה מצחיקה, 'דיאלוג', כיתוב שנון של מימ):\n"
            "   כתוב משפט קצר, קולע ומבדר בעברית (ללא מרכאות).\n"
            "2. דגש עליון וקריטי: לא בכוח! אם התמונה רגילה, שלווה, נופית או שאין בה שום דבר משעשע באמת - החזר מחרוזת ריקה (\"\"). הומור מאולץ הוא גרוע.\n"
            "החזר פלט JSON התואם ל-Schema עם index ו-humorous_description לכל תמונה.\n"
        ]

        for idx, (thumb_img, title, desc) in enumerate(items, 1):
            contents.append(f"תמונה {idx}: {title} | {desc}")
            buf = io.BytesIO()
            thumb_img.save(buf, format="WEBP", quality=80)
            contents.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/webp"))

        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                cfg = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BatchHumorResponse,
                    temperature=0.3,
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=cfg,
                )

                parsed_map = {}
                if response.parsed and isinstance(response.parsed, BatchHumorResponse):
                    for p in response.parsed.items:
                        parsed_map[p.index] = sanitize_text(p.humorous_description)
                elif response.text:
                    raw_data = json.loads(response.text)
                    raw_items = raw_data.get("items", []) if isinstance(raw_data, dict) else raw_data
                    for p in raw_items:
                        idx = p.get("index", len(parsed_map) + 1)
                        parsed_map[idx] = sanitize_text(p.get("humorous_description"))

                results = []
                for idx in range(1, len(items) + 1):
                    results.append(parsed_map.get(idx, ""))

                time.sleep(0.5)
                return results

            except Exception as e:
                err_str = str(e)
                if attempt < max_retries:
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        time.sleep(5.0)
                    else:
                        time.sleep(2.0)
                else:
                    logger.warning(f"שגיאה בהפקת הומור Batch: {e}")
                    return ["" for _ in items]

        return ["" for _ in items]

    def _fallback_tags(self, filename: str) -> PhotoAITags:
        """יצירת נתוני תיוג ברירת מחדל במקרה שאין מפתח או שקרתה תקלה."""
        # ניקוי שם הקובץ ליצירת כותרת בסיסית
        stem = Path(filename).stem
        clean_title = re.sub(r"[-_]+", " ", stem).strip()
        # הסרת חתימות תוכנה מוכרות
        clean_title = re.sub(r"(Topaz|Sharpen|Denoise|Gigapixel|\d+X)", "", clean_title, flags=re.IGNORECASE).strip()

        return PhotoAITags(
            title=sanitize_text(clean_title) or "תמונה מהגלריה",
            title_en=sanitize_text(clean_title) or "Gallery Photo",
            species_hebrew="",
            species_latin="",
            species_en="",
            category="wildlife",
            behavior=[],
            tags=["גלריה", "טבע"],
            tags_en=["gallery", "nature"],
            description="תמונה מאוסף הגלריה.",
            description_en="A photograph from the gallery collection.",
            humorous_description="",
            humorous_description_en="",
        )


# ==============================================================================
# אופטימיזציה, כיווץ ויצירת קבצים
# ==============================================================================

def clean_safe_id(filename: str, existing_ids: Set[str]) -> str:
    """
    יצירת מזהה (ID) בטוח לשימוש ברשת ולשמות קבצים, ללא תווים בעייתיים.
    """
    stem = Path(filename).stem
    # הסרת סימני כיוון בלתי נראים ותווי בקרה
    stem = re.sub(r"[\u200e\u200f\u202a-\u202e\ufeff\u200b\ufffd]", "", stem)
    # החלפת תווים מיוחדים ורווחים בקו תחתי
    safe = re.sub(r"[^\w\-_]+", "_", stem, flags=re.UNICODE)
    safe = re.sub(r"_+", "_", safe).strip("_")
    
    if not safe:
        safe = "photo"

    base_id = safe
    counter = 1
    while safe in existing_ids:
        safe = f"{base_id}_{counter}"
        counter += 1

    existing_ids.add(safe)
    return safe


# ==============================================================================
# ניהול אחסון ענן חיצוני (Cloudflare R2 / S3)
# ==============================================================================

class R2Uploader:
    """ניהול העלאת מדיה ישירות ל-Cloudflare R2 / S3-compatible Object Storage."""

    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        public_url: Optional[str] = None,
    ):
        self.account_id = (account_id or os.getenv("R2_ACCOUNT_ID") or "").strip()
        self.access_key_id = (access_key_id or os.getenv("R2_ACCESS_KEY_ID") or "").strip()
        self.secret_access_key = (secret_access_key or os.getenv("R2_SECRET_ACCESS_KEY") or "").strip()
        self.bucket_name = (bucket_name or os.getenv("R2_BUCKET_NAME") or "").strip()
        self.public_url = (public_url or os.getenv("R2_PUBLIC_URL") or "").strip().rstrip("/")

        self.is_configured = bool(
            HAS_BOTO3
            and self.account_id
            and self.access_key_id
            and self.secret_access_key
            and self.bucket_name
        )

        self.client = None
        if self.is_configured:
            try:
                endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"
                self.client = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name="auto",
                    config=Config(
                        signature_version="s3v4",
                        retries={"max_attempts": 3, "mode": "standard"},
                    ),
                )
            except Exception as e:
                logger.error(f"שגיאה באתחול החיבור ל-Cloudflare R2: {e}")
                self.is_configured = False
                self.client = None

    def get_public_url(self, object_key: str) -> str:
        key = object_key.lstrip("/")
        if self.public_url:
            return f"{self.public_url}/{key}"
        return f"https://{self.bucket_name}.r2.cloudflarestorage.com/{key}"

    def upload_file(self, local_path: Path, object_key: str, content_type: str = "image/webp") -> str:
        """העלאת קובץ מקומי לבאקט של Cloudflare R2 והחזרת ה-URL הציבורי."""
        if not self.is_configured or self.client is None:
            raise RuntimeError("Cloudflare R2 אינו מוגדר כראוי בקובץ .env")

        key = object_key.lstrip("/")
        extra_args = {
            "ContentType": content_type,
            "CacheControl": "public, max-age=31536000, immutable",
        }
        self.client.upload_file(
            Filename=str(local_path),
            Bucket=self.bucket_name,
            Key=key,
            ExtraArgs=extra_args,
        )
        return self.get_public_url(key)


def process_image_file(
    image_path: Path,
    photo_id: str,
    display_dir: Path,
    thumbs_dir: Path,
    r2_uploader: Optional[R2Uploader] = None,
) -> Tuple[Image.Image, Dimensions, RelativePaths, Optional[str], Optional[str]]:
    """
    1. טעינת התמונה וסיבוב לפי EXIF Transpose.
    2. שמירת תמונת Display כ-WebP (איכות 100).
    3. יצירת Thumbnail (רוחב מרבי 500px) ושמירה כ-WebP (איכות 80).
    4. העלאה ישירה ל-Cloudflare R2 / S3 (אם מוגדר).
    5. החזרת אובייקט ה-Thumbnail למטרת תיוג AI, יחד עם ממדים ונתיבים מלאים.
    """
    out_filename = f"{photo_id}.webp"
    display_path = display_dir / out_filename
    thumb_path = thumbs_dir / out_filename

    with Image.open(image_path) as raw_img:
        # סיבוב אוטומטי לפי חיישן הכיוון של המצלמה
        img = ImageOps.exif_transpose(raw_img)

        # המרה ל-RGB אם התמונה במצב שאינו נתמך כראוי (כמו CMYK או פלטה)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        aspect_ratio = round(orig_w / orig_h, 3) if orig_h > 0 else 1.0
        dimensions = Dimensions(width=orig_w, height=orig_h, aspect_ratio=aspect_ratio)

        # 1. שמירת תמונת התצוגה (Display) - ללא Resize, איכות 100
        display_dir.mkdir(parents=True, exist_ok=True)
        img.save(display_path, format="WEBP", quality=DISPLAY_QUALITY, method=6)

        # 2. יצירת Thumbnail - רוחב מרבי 500px ושמירה על יחס ממדים
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        if orig_w > THUMB_MAX_WIDTH:
            new_h = int(orig_h * (THUMB_MAX_WIDTH / orig_w))
            thumb_img = img.resize((THUMB_MAX_WIDTH, new_h), Image.Resampling.LANCZOS)
        else:
            thumb_img = img.copy()

        thumb_img.save(thumb_path, format="WEBP", quality=THUMB_QUALITY, method=6)

        disp_url: Optional[str] = None
        thumb_url: Optional[str] = None

        # 3. העלאה ל-Cloudflare R2 אם מוגדר
        if r2_uploader and r2_uploader.is_configured:
            disp_url = r2_uploader.upload_file(display_path, f"photos/display/{out_filename}", "image/webp")
            thumb_url = r2_uploader.upload_file(thumb_path, f"photos/thumbs/{out_filename}", "image/webp")
            paths = RelativePaths(
                display=disp_url,
                thumbnail=thumb_url,
            )
        else:
            paths = RelativePaths(
                display=f"photos/display/{out_filename}",
                thumbnail=f"photos/thumbs/{out_filename}",
            )

        return thumb_img, dimensions, paths, disp_url, thumb_url


# ==============================================================================
# ניהול נתוני הגלריה ושמירה אינקרמנטלית
# ==============================================================================

class GalleryDatabase:
    """ניהול קובץ photos.json בצורה אינקרמנטלית ועמידה לשגיאות."""

    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.records: Dict[str, PhotoRecord] = {}
        self.existing_ids: Set[str] = set()
        self.processed_filenames: Set[str] = set()
        self._load()

    def _load(self) -> None:
        """טעינת רשומות קיימות מהקובץ אם הוא קיים."""
        if not self.data_file.exists():
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            items = raw_data if isinstance(raw_data, list) else raw_data.get("photos", [])
            for item in items:
                try:
                    record = PhotoRecord(**item)
                    self.records[record.original_filename] = record
                    self.existing_ids.add(record.id)
                    self.processed_filenames.add(record.original_filename)
                except Exception as e:
                    logger.debug(f"דילוג על רשומה לא תקינה בקובץ JSON: {e}")

            logger.info(f"נטענו {len(self.records)} רשומות קיימות מתוך {self.data_file.name}.")
        except Exception as e:
            logger.warning(f"שגיאה בקריאת {self.data_file}: {e}. ייווצר קובץ חדש.")

    def is_processed(self, filename: str, display_dir: Path, thumbs_dir: Path) -> bool:
        """
        בדיקה האם התמונה כבר עובדה (בענן R2 או מקומית על הדיסק).
        """
        if filename not in self.records:
            return False
        
        record = self.records[filename]

        # אם לתמונה כבר יש URL מלא בענן, נחשבת מעובדת
        if (record.display_url and record.display_url.startswith("http")) or \
           (record.paths and record.paths.display.startswith("http")):
            return True

        disp_file = display_dir / record.filename
        thumb_file = thumbs_dir / record.filename

        return disp_file.exists() and thumb_file.exists()

    def add_record(self, record: PhotoRecord) -> None:
        """הוספה/עדכון של רשומה ומעקב."""
        self.records[record.original_filename] = record
        self.existing_ids.add(record.id)
        self.processed_filenames.add(record.original_filename)

    def save(self) -> None:
        """
        שמירה אטומית של כל הנתונים לתוך photos.json דרך קובץ זמני.
        """
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.data_file.with_suffix(".tmp")

        # מיון הרשומות לפי תאריך צילום (אם קיים) או שם קובץ
        sorted_records = sorted(
            self.records.values(),
            key=lambda r: (r.exif.date_time_original or "", r.original_filename),
            reverse=True,
        )

        data = [r.model_dump() for r in sorted_records]

        for attempt in range(5):
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                temp_file.replace(self.data_file)
                break
            except (PermissionError, OSError) as e:
                if attempt < 4:
                    time.sleep(0.5)
                else:
                    logger.error(f"שגיאה בשמירת קובץ הנתונים {self.data_file}: {e}")
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except OSError:
                            pass


# ==============================================================================
# תהליך העבודה הראשי (Main Pipeline)
# ==============================================================================

def scan_source_directory(source_dir: Path) -> List[Path]:
    """סריקת כל קובצי התמונות הנתמכים בתיקיית המקור."""
    if not source_dir.exists():
        logger.error(f"תיקיית המקור אינה קיימת: {source_dir}")
        return []

    images: List[Path] = []
    for entry in source_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            images.append(entry)

    images.sort(key=lambda p: p.name)
    return images


def process_gallery(
    source_dir: Path = Path(DEFAULT_SOURCE_DIR),
    display_dir: Path = DEFAULT_DISPLAY_DIR,
    thumbs_dir: Path = DEFAULT_THUMBS_DIR,
    data_file: Path = DEFAULT_DATA_FILE,
    limit: Optional[int] = None,
    force: bool = False,
    skip_ai: bool = False,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    no_r2: bool = False,
) -> None:
    """
    ריצת ה-Pipeline השלם:
    - סריקה
    - דילוג אינקרמנטלי
    - עיבוד ואופטימיזציה (WebP)
    - העלאה לענן Cloudflare R2 (אם מוגדר)
    - חילוץ EXIF
    - תיוג AI במקבצים (Batch)
    - שמירה ל-JSON
    """
    print("\n" + "=" * 65)
    print("[START] מתחיל תהליך עיבוד התמונות לגלריה")
    print(f"[-] תיקיית מקור:  {source_dir}")
    print(f"[-] תמונות תצוגה: {display_dir}")
    print(f"[-] Thumbnails:   {thumbs_dir}")
    print(f"[-] קובץ נתונים:  {data_file}")
    print(f"[-] גודל מקבץ AI: {batch_size} תמונות לבקשה")
    print("=" * 65 + "\n")

    # 1. טעינת מסד הנתונים הקיים
    db = GalleryDatabase(data_file)

    # 2. אתחול מודול תיוג ה-AI
    ai_tagger = None
    if not skip_ai:
        ai_tagger = AITagger(model_name=gemini_model)
    else:
        logger.info("הופעל דגל --skip-ai: דילוג על פניות ל-Gemini API.")

    # 3. אתחול מעלה הענן ל-Cloudflare R2
    r2_uploader: Optional[R2Uploader] = None
    if not no_r2:
        r2_uploader = R2Uploader()
        if r2_uploader.is_configured:
            logger.info(f"Cloudflare R2 מופעל: תמונות יועלו ישירות לבאקט '{r2_uploader.bucket_name}'.")
        else:
            logger.info("Cloudflare R2 אינו מוגדר ב-.env: תמונות נשמרות מקומית בלבד ב-public/photos/.")

    # 4. סריקת קובצי מקור
    image_files = scan_source_directory(source_dir)
    total_found = len(image_files)
    logger.info(f"נמצאו {total_found} קובצי תמונות בתיקיית המקור.")

    if not image_files:
        logger.warning("אין תמונות לעיבוד. מסיים.")
        return

    # 5. סינון אינקרמנטלי: איתור תמונות חדשות בלבד
    pending_files: List[Path] = []
    skipped_count = 0

    for img_path in image_files:
        if not force and db.is_processed(img_path.name, display_dir, thumbs_dir):
            skipped_count += 1
        else:
            pending_files.append(img_path)

    logger.info(f"תמונות שכבר עובדו ודולגו: {skipped_count}")
    logger.info(f"תמונות הממתינות לעיבוד:   {len(pending_files)}")

    if limit and limit > 0:
        pending_files = pending_files[:limit]
        logger.info(f"הוגבל ל-{limit} תמונות בלבד (דגל --limit).")

    if not pending_files:
        print("\n✨ כל התמונות כבר מעובדות ומעודכנות! אין צורך בעיבוד קבצים חדשים.\n")
        if not skip_ai and ai_tagger and ai_tagger.is_available:
            missing_humor = [r for r in db.records.values() if r.ai.humorous_description is None]
            if missing_humor:
                logger.info(f"מפעיל הפקת תיאורים הומוריסטיים עבור {len(missing_humor)} תמונות שטרם נותחו...")
                generate_humor_for_gallery(
                    data_file=data_file,
                    thumbs_dir=thumbs_dir,
                    gemini_model=gemini_model,
                    batch_size=10,
                )
        return

    # 6. לולאת עיבוד במקבצים (Batch) לחסכון מרבי בבקשות ובזמן
    success_count = 0
    errors_count = 0

    progress_bar = tqdm(
        total=len(pending_files),
        desc="Processing",
        unit="img",
        dynamic_ncols=True,
    )

    for i in range(0, len(pending_files), batch_size):
        chunk_files = pending_files[i : i + batch_size]
        batch_items = []
        batch_ai_inputs = []

        for img_path in chunk_files:
            filename = img_path.name
            try:
                # א. מזהה ייחודי ובטוח
                photo_id = clean_safe_id(filename, db.existing_ids)

                # ב. טעינה מקדימה וחילוץ EXIF
                with Image.open(img_path) as test_img:
                    exif_data = extract_exif(img_path, test_img)

                # ג. עיבוד תמונה: סיבוב EXIF, שמירת Display (Q100), שמירת Thumb (500px, Q80), והעלאה ל-R2 אם מוגדר
                thumb_img, dimensions, paths, disp_url, thumb_url = process_image_file(
                    image_path=img_path,
                    photo_id=photo_id,
                    display_dir=display_dir,
                    thumbs_dir=thumbs_dir,
                    r2_uploader=r2_uploader,
                )

                batch_items.append({
                    "id": photo_id,
                    "filename": f"{photo_id}.webp",
                    "original_filename": filename,
                    "display_url": disp_url,
                    "thumb_url": thumb_url,
                    "paths": paths,
                    "dimensions": dimensions,
                    "exif": exif_data,
                })
                batch_ai_inputs.append((thumb_img, filename))

            except Exception as e:
                errors_count += 1
                logger.error(f"שגיאה בעיבוד התמונה '{filename}': {e}", exc_info=False)
                progress_bar.update(1)

        if not batch_items:
            continue

        progress_bar.set_postfix_str(f"AI Batch {len(batch_ai_inputs)} imgs...")

        # ד. תיוג AI מרוכז במקבץ (Batch) בבקשת API אחת בלבד!
        if ai_tagger and ai_tagger.is_available:
            ai_tags_list = ai_tagger.tag_batch(batch_ai_inputs)
        else:
            ai_tags_list = [
                ai_tagger._fallback_tags(fn) if ai_tagger else PhotoAITags(
                    title=Path(fn).stem,
                    species_hebrew="",
                    species_latin="",
                    category="wildlife",
                    behavior=[],
                    tags=["טבע"],
                    description="תמונה מהגלריה"
                )
                for _, fn in batch_ai_inputs
            ]

        # ה. הוספה לרשומות ושמירה רציפה
        for idx_b, item in enumerate(batch_items):
            if idx_b < len(ai_tags_list):
                ai_tags = ai_tags_list[idx_b]
            else:
                ai_tags = ai_tagger._fallback_tags(item["original_filename"]) if ai_tagger else PhotoAITags(
                    title=Path(item["original_filename"]).stem,
                    tags=["טבע"],
                    description="תמונה מהגלריה"
                )
            record = PhotoRecord(
                id=item["id"],
                filename=item["filename"],
                original_filename=item["original_filename"],
                display_url=item.get("display_url"),
                thumb_url=item.get("thumb_url"),
                paths=item["paths"],
                dimensions=item["dimensions"],
                exif=item["exif"],
                ai=ai_tags,
                processed_at=datetime.now().isoformat(),
            )
            db.add_record(record)
            success_count += 1

        db.save()
        progress_bar.update(len(batch_items))

    # 6. סיכום ריצה
    print("\n" + "=" * 65)
    print("[SUCCESS] סיום עיבוד התמונות בהצלחה!")
    print(f"[+] תמונות שעובדו בהצלחה: {success_count}")
    print(f"[+] תמונות שדולגו:         {skipped_count}")
    if errors_count > 0:
        print(f"[!] שגיאות:               {errors_count}")
    print(f"[=] סך הכל תמונות בגלריה: {len(db.records)}")
    print(f"[*] קובץ נתונים מעודכן:   {data_file}")
    print("=" * 65 + "\n")

    # 7. השלמת מצב הומוריסטי לתמונות קיימות שטרם נותחו
    if not skip_ai and ai_tagger and ai_tagger.is_available:
        missing_humor = [r for r in db.records.values() if r.ai.humorous_description is None]
        if missing_humor:
            logger.info(f"מפעיל הפקת תיאורים הומוריסטיים עבור {len(missing_humor)} תמונות קיימות שטרם נותחו...")
            generate_humor_for_gallery(
                data_file=data_file,
                thumbs_dir=thumbs_dir,
                gemini_model=gemini_model,
                batch_size=10,
            )


def is_fallback_ai(ai: PhotoAITags, orig_filename: str) -> bool:
    """זיהוי האם תיוג ה-AI של התמונה הוא ברירת מחדל / חסר / נכשל."""
    desc = (ai.description or "").strip()
    title = (ai.title or "").strip()
    tags = ai.tags or []
    if desc in ["תמונה מאוסף הגלריה.", "תמונה מהגלריה", ""]:
        return True
    if not title or title == orig_filename:
        return True
    if any(k in title for k in ["RG5", "RG7", "Topaz", "Enhanced", "IMG_"]):
        return True
    if tags == ["טבע"] and not ai.species_hebrew and desc == "תמונה מהגלריה":
        return True
    return False


def retag_fallback_photos(
    data_file: Path = DEFAULT_DATA_FILE,
    thumbs_dir: Path = DEFAULT_THUMBS_DIR,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """
    איתור כל התמונות שבהן תיוג ה-AI התפספס או השתמש בברירת מחדל,
    ותיוג חוזר שלהן בלבד דרך ה-Thumbnails הקיימים.
    """
    print("\n" + "=" * 65)
    print("[START] איתור ותיוג מחדש של תמונות עם תיוג חלקי / ברירת מחדל")
    print(f"[-] קובץ נתונים:  {data_file}")
    print(f"[-] Thumbnails:   {thumbs_dir}")
    print(f"[-] גודל מקבץ AI: {batch_size} תמונות לבקשה")
    print(f"[-] מודל:         {gemini_model}")
    print("=" * 65 + "\n")

    db = GalleryDatabase(data_file)
    ai_tagger = AITagger(model_name=gemini_model)
    if not ai_tagger.is_available:
        print("[ERROR] מפתח Gemini API אינו מוגדר או אינו זמין!")
        return

    to_fix: List[PhotoRecord] = []
    for record in db.records.values():
        if is_fallback_ai(record.ai, record.original_filename):
            to_fix.append(record)

    print(f"[INFO] נמצאו {len(to_fix)} תמונות הדורשות תיוג מחדש.")
    if not to_fix:
        print("[SUCCESS] כל התמונות בגלריה מתויגות באופן תקין ומלא!")
        return

    progress_bar = tqdm(total=len(to_fix), desc="Re-tagging AI", unit="img")
    fixed_count = 0

    for i in range(0, len(to_fix), batch_size):
        batch_records = to_fix[i : i + batch_size]
        batch_items: List[Tuple[Image.Image, str]] = []

        for rec in batch_records:
            thumb_path = thumbs_dir / rec.filename
            if not thumb_path.exists():
                thumb_path = thumbs_dir / Path(rec.paths.thumbnail).name
            if thumb_path.exists():
                try:
                    img = Image.open(thumb_path)
                    img.load()
                    batch_items.append((img, rec.original_filename))
                except Exception as e:
                    logger.warning(f"שגיאה בפתיחת thumbnail {thumb_path}: {e}")
            else:
                logger.warning(f"לא נמצא thumbnail עבור {rec.original_filename}")

        if batch_items:
            progress_bar.set_postfix_str(f"AI Batch {len(batch_items)} imgs...")
            ai_tags_list = ai_tagger.tag_batch(batch_items)

            for idx_b, rec in enumerate(batch_records):
                if idx_b < len(ai_tags_list):
                    new_tags = ai_tags_list[idx_b]
                    if not is_fallback_ai(new_tags, rec.original_filename):
                        rec.ai = new_tags
                        rec.processed_at = datetime.now().isoformat()
                        db.add_record(rec)
                        fixed_count += 1

            db.save()

        progress_bar.update(len(batch_records))

    progress_bar.close()
    print("\n" + "=" * 65)
    print(f"[SUCCESS] סיום תיוג מחדש! {fixed_count} תמונות עודכנו בהצלחה.")
    print(f"[*] קובץ נתונים מעודכן: {data_file}")
    print("=" * 65 + "\n")


def generate_humor_for_gallery(
    data_file: Path = DEFAULT_DATA_FILE,
    thumbs_dir: Path = DEFAULT_THUMBS_DIR,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    batch_size: int = 10,
    force_all: bool = False,
) -> None:
    """
    הפקת תיאורים הומוריסטיים (מצב משעשע) עבור כל תמונות הגלריה שטרם נותחו.
    שולח במקבצים של 10 תמונות ל-Gemini Flash.
    """
    print("\n" + "=" * 65)
    print("[START] הפקת תיאורים הומוריסטיים (מצב משעשע) לתמונות הגלריה")
    print(f"[-] קובץ נתונים:  {data_file}")
    print(f"[-] Thumbnails:   {thumbs_dir}")
    print(f"[-] גודל מקבץ AI: {batch_size} תמונות לבקשה")
    print(f"[-] מודל:         {gemini_model}")
    print("=" * 65 + "\n")

    db = GalleryDatabase(data_file)
    ai_tagger = AITagger(model_name=gemini_model)
    if not ai_tagger.is_available:
        print("[ERROR] מפתח Gemini API אינו מוגדר או אינו זמין!")
        return

    # איתור תמונות שטרם נבדקו למצב הומוריסטי
    to_process: List[PhotoRecord] = []
    for record in db.records.values():
        if force_all or record.ai.humorous_description is None:
            to_process.append(record)

    print(f"[INFO] נמצאו {len(to_process)} תמונות הממתינות לבדיקה/הפקת הומור.")
    if not to_process:
        print("[SUCCESS] כל התמונות כבר עברו ניתוח הומוריסטי!")
        return

    progress_bar = tqdm(total=len(to_process), desc="Humor Processing", unit="img")
    funny_count = 0

    for i in range(0, len(to_process), batch_size):
        batch_records = to_process[i : i + batch_size]
        batch_items: List[Tuple[Image.Image, str, str]] = []
        valid_records: List[PhotoRecord] = []

        for rec in batch_records:
            thumb_path = thumbs_dir / rec.filename
            if not thumb_path.exists():
                thumb_path = thumbs_dir / Path(rec.paths.thumbnail).name
            if thumb_path.exists():
                try:
                    img = Image.open(thumb_path)
                    img.load()
                    batch_items.append((img, rec.ai.title, rec.ai.description))
                    valid_records.append(rec)
                except Exception as e:
                    logger.warning(f"שגיאה בפתיחת thumbnail {thumb_path}: {e}")
                    rec.ai.humorous_description = ""
            else:
                logger.warning(f"לא נמצא thumbnail עבור {rec.original_filename}")
                rec.ai.humorous_description = ""

        if batch_items:
            progress_bar.set_postfix_str(f"AI Batch {len(batch_items)} imgs...")
            humor_list = ai_tagger.tag_humor_batch(batch_items)

            for rec, humor in zip(valid_records, humor_list):
                rec.ai.humorous_description = humor
                if humor:
                    funny_count += 1
                db.add_record(rec)

            db.save()

        progress_bar.update(len(batch_records))

    progress_bar.close()
    print("\n" + "=" * 65)
    print(f"[SUCCESS] סיום הפקת מצב הומוריסטי! הופקו {funny_count} תיאורים משעשעים מתוך {len(to_process)} תמונות שנבדקו.")
    print(f"[*] קובץ נתונים מעודכן: {data_file}")
    print("=" * 65 + "\n")


def migrate_existing_to_r2(
    data_file: Path = DEFAULT_DATA_FILE,
    display_dir: Path = DEFAULT_DISPLAY_DIR,
    thumbs_dir: Path = DEFAULT_THUMBS_DIR,
) -> None:
    """
    העלאת כל התמונות הקיימות שכבר עובדו מקומית ל-Cloudflare R2,
    ועדכון קובץ photos.json עם כתובות ה-CDN המלאות (ללא צורך בהרצה חוזרת של AI).
    """
    r2_uploader = R2Uploader()

    if not r2_uploader.is_configured:
        print("\n" + "=" * 65)
        print("[ERROR] פרטי Cloudflare R2 אינם מוגדרים במלואם בקובץ .env!")
        print("נא לוודא שמוגדרים המשתנים הבאים ב-.env:")
        print("  - R2_ACCOUNT_ID")
        print("  - R2_ACCESS_KEY_ID")
        print("  - R2_SECRET_ACCESS_KEY")
        print("  - R2_BUCKET_NAME")
        print("  - R2_PUBLIC_URL")
        print("=" * 65 + "\n")
        return

    db = GalleryDatabase(data_file)
    records = list(db.records.values())
    if not records:
        print("[INFO] אין רשומות בקובץ photos.json.")
        return

    to_upload: List[PhotoRecord] = []
    for r in records:
        disp_remote = (r.display_url and r.display_url.startswith("http")) or r.paths.display.startswith("http")
        thumb_remote = (r.thumb_url and r.thumb_url.startswith("http")) or r.paths.thumbnail.startswith("http")
        if not (disp_remote and thumb_remote):
            to_upload.append(r)

    print("\n" + "=" * 65)
    print("[MIGRATE] העלאת תמונות קיימות ל-Cloudflare R2")
    print(f"[-] סך הכל תמונות במסד:    {len(records)}")
    print(f"[-] תמונות הדורשות העלאה: {len(to_upload)}")
    print(f"[-] באקט יעד:               {r2_uploader.bucket_name}")
    print(f"[-] דומיין ציבורי:         {r2_uploader.public_url or 'ברירת מחדל של R2'}")
    print("=" * 65 + "\n")

    if not to_upload:
        print("[SUCCESS] כל התמונות בגלריה כבר מועלות ומקושרות ל-Cloudflare R2!\n")
        return

    progress_bar = tqdm(total=len(to_upload), desc="Uploading to R2", unit="img")
    uploaded_count = 0
    errors_count = 0

    for rec in to_upload:
        filename = rec.filename or f"{rec.id}.webp"
        disp_file = display_dir / filename
        thumb_file = thumbs_dir / filename

        # בדיקת נתיב גיבוי אם השם שונה מעט
        if not disp_file.exists():
            disp_file = display_dir / Path(rec.paths.display).name
        if not thumb_file.exists():
            thumb_file = thumbs_dir / Path(rec.paths.thumbnail).name

        try:
            if not disp_file.exists() or not thumb_file.exists():
                logger.warning(f"קובץ מקומי חסר עבור {rec.id} ({filename}) - דילוג.")
                errors_count += 1
                progress_bar.update(1)
                continue

            disp_key = f"photos/display/{filename}"
            thumb_key = f"photos/thumbs/{filename}"

            disp_url = r2_uploader.upload_file(disp_file, disp_key, "image/webp")
            thumb_url = r2_uploader.upload_file(thumb_file, thumb_key, "image/webp")

            rec.display_url = disp_url
            rec.thumb_url = thumb_url
            rec.paths.display = disp_url
            rec.paths.thumbnail = thumb_url

            db.add_record(rec)
            uploaded_count += 1

            if uploaded_count % 10 == 0:
                db.save()

        except Exception as e:
            errors_count += 1
            logger.error(f"שגיאה בהעלאת {rec.id} ל-R2: {e}")

        progress_bar.update(1)

    db.save()
    progress_bar.close()

    print("\n" + "=" * 65)
    print("[SUCCESS] סיום העלאת התמונות ל-Cloudflare R2!")
    print(f"[+] תמונות שהועלו ועודכנו: {uploaded_count}")
    if errors_count > 0:
        print(f"[!] תקלות:                  {errors_count}")
    print(f"[*] קובץ נתונים מעודכן:     {data_file}")
    print("=" * 65 + "\n")


# ==============================================================================
# ממשק שורת הפקודה (CLI Entrypoint)
# ==============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="סקריפט עיבוד, חילוץ EXIF ותיוג AI עבור גלריית תמונות."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(DEFAULT_SOURCE_DIR),
        help=f"נתיב לתיקיית תמונות המקור (ברירת מחדל: '{DEFAULT_SOURCE_DIR}')",
    )
    parser.add_argument(
        "--display-dir",
        type=Path,
        default=DEFAULT_DISPLAY_DIR,
        help="תיקיית יעד לתמונות תצוגה WebP",
    )
    parser.add_argument(
        "--thumbs-dir",
        type=Path,
        default=DEFAULT_THUMBS_DIR,
        help="תיקיית יעד ל-Thumbnails WebP",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help="קובץ JSON מרכזי לנתוני הגלריה",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="הגבלת מספר התמונות לעיבוד (שימושי לבדיקות)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"מספר תמונות שנשלחות יחד בבקשת AI אחת (ברירת מחדל: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="עיבוד מחדש של כל התמונות גם אם כבר קיימות ב-JSON",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="ביצוע עיבוד תמונות ו-EXIF בלבד ללא קריאה ל-Gemini API",
    )
    parser.add_argument(
        "--retag-fallback",
        action="store_true",
        help="איתור ותיוג מחדש ב-AI בלבד של כל התמונות שבהן התיוג נכשל או השתמש בברירת מחדל",
    )
    parser.add_argument(
        "--add-humor",
        action="store_true",
        help="הפקת תיאור הומוריסטי/משעשע עבור כל התמונות שטרם נותחו",
    )
    parser.add_argument(
        "--force-humor",
        action="store_true",
        help="הפקה מחדש של תיאור הומוריסטי לכל התמונות גם אם כבר נותחו",
    )
    parser.add_argument(
        "--migrate-r2",
        "--upload-existing-to-r2",
        action="store_true",
        dest="migrate_r2",
        help="העלאת כל התמונות הקיימות שכבר עובדו מקומית ל-Cloudflare R2 ועדכון ה-JSON",
    )
    parser.add_argument(
        "--no-r2",
        action="store_true",
        help="שמירת קבצים מקומית בלבד ללא העלאה ל-Cloudflare R2",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_GEMINI_MODEL,
        help=f"שם מודל ה-Gemini לשימוש (ברירת מחדל: {DEFAULT_GEMINI_MODEL})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    if cli_args.migrate_r2:
        migrate_existing_to_r2(
            data_file=cli_args.data_file,
            display_dir=cli_args.display_dir,
            thumbs_dir=cli_args.thumbs_dir,
        )
    elif cli_args.retag_fallback:
        retag_fallback_photos(
            data_file=cli_args.data_file,
            thumbs_dir=cli_args.thumbs_dir,
            gemini_model=cli_args.model,
            batch_size=cli_args.batch_size,
        )
    elif cli_args.add_humor or cli_args.force_humor:
        generate_humor_for_gallery(
            data_file=cli_args.data_file,
            thumbs_dir=cli_args.thumbs_dir,
            gemini_model=cli_args.model,
            batch_size=10,
            force_all=cli_args.force_humor,
        )
    else:
        process_gallery(
            source_dir=cli_args.source,
            display_dir=cli_args.display_dir,
            thumbs_dir=cli_args.thumbs_dir,
            data_file=cli_args.data_file,
            limit=cli_args.limit,
            force=cli_args.force,
            skip_ai=cli_args.skip_ai,
            gemini_model=cli_args.model,
            batch_size=cli_args.batch_size,
            no_r2=cli_args.no_r2,
        )
