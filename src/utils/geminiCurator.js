// geminiCurator.js - AI Curator service powered by Gemini API
import { db, isUserOwner } from './firebase.js';
import { doc, getDoc, setDoc } from 'firebase/firestore';

const DEFAULT_API_KEY = typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_GEMINI_API_KEY 
  ? import.meta.env.PUBLIC_GEMINI_API_KEY 
  : '';

/**
 * Retrieve Gemini API key:
 * Checks Firestore admin_config/secrets if user is owner, or falls back to env/localStorage
 */
export const getGeminiApiKey = async (user) => {
  // 1. Check local storage cache
  try {
    const local = localStorage.getItem('curator_gemini_key');
    if (local && local.startsWith('AIzaSy')) return local;
  } catch (e) {}

  // 2. If user is owner, try to fetch from Firestore admin_config/secrets
  if (db && isUserOwner(user)) {
    try {
      const snap = await getDoc(doc(db, 'admin_config', 'secrets'));
      if (snap.exists() && snap.data().gemini_api_key) {
        const key = snap.data().gemini_api_key;
        try { localStorage.setItem('curator_gemini_key', key); } catch (e) {}
        return key;
      }
    } catch (e) {
      console.warn('Could not read admin_config/secrets:', e);
    }
  }

  return DEFAULT_API_KEY;
};

export const saveGeminiApiKey = async (key, user) => {
  const clean = key.trim();
  try {
    localStorage.setItem('curator_gemini_key', clean);
  } catch (e) {}

  if (db && isUserOwner(user)) {
    try {
      await setDoc(doc(db, 'admin_config', 'secrets'), {
        gemini_api_key: clean
      }, { merge: true });
    } catch (e) {
      console.warn('Failed to save key in Firestore:', e);
    }
  }
};

/**
 * Request Gemini critique for a single exhibition candidate
 */
export const requestPhotoCritique = async (photo, apiKey) => {
  if (!apiKey) throw new Error('נא להזין מפתח Gemini API כדי להשתמש באוצר הדיגיטלי.');

  const prompt = `אתה אוצר בכיר של גלריית צילום טבע ואמנות יוקרתית. 
צלם הטבע רועי גרינברג שוקל לכלול את התצלום הבא בתערוכת יחיד או בקיר תמונות מרכזי.

פרטי התצלום:
- כותרת: ${photo.title || photo.title_en || 'ללא כותרת'}
- מין / נושא: ${photo.species_he || photo.species_en || 'כללי'}
- קטגוריה: ${photo.category || photo.categoryHe || 'צילום טבע'}
- נתוני צילום (EXIF):
  * מצלמה: ${photo.exif?.camera_model || 'לא צוין'}
  * עדשה: ${photo.exif?.lens_model || 'לא צוין'}
  * מוקד: ${photo.exif?.focal_length || 'לא צוין'}
  * צמצם: ${photo.exif?.aperture || 'לא צוין'}
  * תריס: ${photo.exif?.shutter_speed || 'לא צוין'}
  * ISO: ${photo.exif?.iso || 'לא צוין'}

אנא ספק ניתוח אוצרותי מקצועי, חד, ענייני וכן (בעברית רהוטה ונעימה), במבנה הבא:
1. 🌟 **רושם ראשוני ועוצמה רגשית / ויזואלית** (מדוע התמונה לוכדת את העין?)
2. 📐 **קומפוזיציה, אור וחדות טכנית** (הולכת עין, ניקיון הרקע, עומק שדה)
3. 🖼️ **התאמה להדפסה גדולה בתערוכה** (האם הפריים מתאים להדפסה ברוחב מטר ומעלה? נקודות לשים לב אליהן)
4. 💡 **הכרעה והמלצת אוצר**: האם התמונה הזו היא מועמדת בטוחה (חובה), אפשרית, או מתאימה יותר לקיר תמונות?`;

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{
        parts: [{ text: prompt }]
      }]
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`שגיאת Gemini API: ${response.status} - ${errText}`);
  }

  const result = await response.json();
  const text = result.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error('לא התקבלה תשובה מ-Gemini');
  return text;
};

/**
 * Request Gemini head-to-head comparison for a sub-group
 */
export const requestGroupComparison = async (groupName, photos, apiKey) => {
  if (!apiKey) throw new Error('נא להזין מפתח Gemini API כדי להשתמש באוצר הדיגיטלי.');
  if (!photos || photos.length < 2) throw new Error('נדרשות לפחות 2 תמונות להשוואה.');

  const photosListText = photos.map((p, idx) => `
תמונה #${idx + 1}:
- מזהה: ${p.id}
- כותרת: ${p.photo_data?.title || p.title || 'ללא'}
- מין: ${p.photo_data?.species_he || p.species_he || 'לא צוין'}
- EXIF: מצלמה: ${p.photo_data?.exif?.camera_model || 'לא ידוע'}, צמצם: ${p.photo_data?.exif?.aperture || 'לא ידוע'}, תריס: ${p.photo_data?.exif?.shutter_speed || 'לא ידוע'}, ISO: ${p.photo_data?.exif?.iso || 'לא ידוע'}
- הערות/הומור: ${p.photo_data?.humorous_description || ''}
`).join('\n---\n');

  const prompt = `אתה אוצר אמנות וצילום טבע. צלם הטבע רועי גרינברג יצר תת-קבוצה בשם "${groupName}" עם ${photos.length} תמונות שמתחרות ראש בראש על מקום יחיד בתערוכה.

התמונות המתחרות:
${photosListText}

אנא ספק השוואה אוצרותית מנומקת (בעברית):
1. **השוואה קצרה**: מה היתרון הבולט של כל תמונה?
2. 🏆 **הכרעת האוצר - המנצחת**: איזו תמונה היא הטובה ביותר לתערוכה ראשית ולמה?
3. 🥈 **המלצה למקום השני**: האם לשמור אותה כחלופה או להעביר אותה לקיר תמונות?`;

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{
        parts: [{ text: prompt }]
      }]
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`שגיאת Gemini API: ${response.status} - ${errText}`);
  }

  const result = await response.json();
  const text = result.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error('לא התקבלה תשובה מ-Gemini');
  return text;
};
