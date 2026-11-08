// uploaderService.js - Client-Side Owner Photo Processing & Cloudflare R2 Upload Pipeline
import exifr from 'exifr';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { db, isUserOwner } from './firebase.js';
import { collection, addDoc, serverTimestamp } from 'firebase/firestore';
import speciesRegistry from '../data/species_registry.json';

export const R2_CONFIG = {
  accountId: '17810f22ce3ee57341e89107ed1c2913',
  bucketName: 'my-photo-gallery',
  publicUrl: 'https://pub-d8a9140bbd28466cb778bf724fb793b0.r2.dev',
  accessKeyId: 'a8f1004c8a901986701a97d3b4a00321',
  secretAccessKey: 'b1c46e07f2ccb8e2de8a09b29d6e44e6ac0dac9e8afac921f8d495641f9dd3aa'
};

/**
 * Extract EXIF metadata from raw File
 */
export const extractExifFromFile = async (file) => {
  try {
    const rawExif = await exifr.parse(file, [
      'Make',
      'Model',
      'LensModel',
      'LensMake',
      'FocalLength',
      'FNumber',
      'ExposureTime',
      'ISO',
      'DateTimeOriginal',
      'CreateDate',
      'ImageWidth',
      'ImageHeight'
    ]);

    if (!rawExif) {
      return {
        camera: 'לא ידוע',
        camera_model: '',
        lens: 'לא צוין',
        lens_model: '',
        focalLength: '',
        focal_length: '',
        aperture: '',
        shutterSpeed: '',
        shutter_speed: '',
        iso: '',
        date: new Date().toLocaleDateString('he-IL'),
        date_time_original: ''
      };
    }

    // Format shutter speed (e.g., 1/1600s)
    let shutterStr = '';
    if (rawExif.ExposureTime) {
      if (rawExif.ExposureTime < 1) {
        shutterStr = `1/${Math.round(1 / rawExif.ExposureTime)}s`;
      } else {
        shutterStr = `${rawExif.ExposureTime}s`;
      }
    }

    const apertureStr = rawExif.FNumber ? `f/${rawExif.FNumber}` : '';
    const focalStr = rawExif.FocalLength ? `${Math.round(rawExif.FocalLength)}mm` : '';
    const cameraStr = rawExif.Model ? `${rawExif.Make || ''} ${rawExif.Model}`.trim() : (rawExif.Make || 'לא ידוע');
    const lensStr = rawExif.LensModel || 'לא צוין';
    const isoStr = rawExif.ISO ? String(rawExif.ISO) : '';

    let dateStr = '';
    let rawDateStr = '';
    if (rawExif.DateTimeOriginal || rawExif.CreateDate) {
      const d = new Date(rawExif.DateTimeOriginal || rawExif.CreateDate);
      if (!isNaN(d.getTime())) {
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const yyyy = d.getFullYear();
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        const ss = String(d.getSeconds()).padStart(2, '0');
        dateStr = `${dd}/${mm}/${yyyy} ${hh}:${min}:${ss}`;
        rawDateStr = `${yyyy}:${mm}:${dd} ${hh}:${min}:${ss}`;
      }
    }

    return {
      camera: cameraStr,
      camera_model: cameraStr,
      lens: lensStr,
      lens_model: lensStr,
      focalLength: focalStr,
      focal_length: focalStr,
      aperture: apertureStr,
      shutterSpeed: shutterStr,
      shutter_speed: shutterStr,
      iso: isoStr,
      date: dateStr || new Date().toLocaleDateString('he-IL'),
      date_time_original: rawDateStr
    };
  } catch (err) {
    console.warn('EXIF extraction failed, using fallback:', err);
    return {
      camera: 'לא ידוע',
      camera_model: '',
      lens: 'לא צוין',
      lens_model: '',
      focalLength: '',
      focal_length: '',
      aperture: '',
      shutterSpeed: '',
      shutter_speed: '',
      iso: '',
      date: new Date().toLocaleDateString('he-IL'),
      date_time_original: ''
    };
  }
};

/**
 * Resize and convert an Image to WebP Blob using HTML5 Canvas
 */
export const resizeImageToWebP = (file, maxDimension, quality = 0.85) => {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;

      if (width > maxDimension || height > maxDimension) {
        if (width >= height) {
          height = Math.round((height * maxDimension) / width);
          width = maxDimension;
        } else {
          width = Math.round((width * maxDimension) / height);
          height = maxDimension;
        }
      }

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;

      const ctx = canvas.getContext('2d');
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('Canvas WebP export failed'));
          return;
        }
        resolve({
          blob,
          width,
          height,
          aspectRatio: (width / height).toFixed(2)
        });
      }, 'image/webp', quality);
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Failed to load image file'));
    };

    img.src = url;
  });
};

/**
 * Upload WebP Blob directly to Cloudflare R2
 */
export const uploadBlobToR2 = async (blob, objectKey) => {
  const s3 = new S3Client({
    region: 'auto',
    endpoint: `https://${R2_CONFIG.accountId}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: R2_CONFIG.accessKeyId,
      secretAccessKey: R2_CONFIG.secretAccessKey
    }
  });

  const arrayBuffer = await blob.arrayBuffer();
  const cleanKey = objectKey.replace(/^\//, '');
  const command = new PutObjectCommand({
    Bucket: R2_CONFIG.bucketName,
    Key: cleanKey,
    Body: new Uint8Array(arrayBuffer),
    ContentType: 'image/webp',
    CacheControl: 'public, max-age=31536000'
  });

  await s3.send(command);
  return `${R2_CONFIG.publicUrl}/${cleanKey}`;
};

/**
 * Analyze image and generate bilingual metadata using Gemini API
 */
export const generatePhotoMetadataWithGemini = async (imageDisplayBlob, exifData, apiKey) => {
  if (!apiKey) throw new Error('Gemini API key is required');

  // Convert blob to base64
  const base64Data = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64 = reader.result.split(',')[1];
      resolve(base64);
    };
    reader.readAsDataURL(imageDisplayBlob);
  });

  const prompt = `אתה בוט מומחה לצילום טבע, זואולוגיה ובוטניקה בישראל עבור גלריית הצילום של רועי גרינברג.
נתח את התצלום המצורף והחזר אך ורק אובייקט JSON תקין (ללא markdown וללא הערות) במבנה הבא:

{
  "title": "כותרת קולעת בעברית",
  "title_en": "Fitting Title in English",
  "species_hebrew": "שם המין בעברית (מדויק)",
  "species_latin": "Scientific Latin Name",
  "species_en": "Official English Name",
  "category": "wildlife", // אחת מתוך: wildlife, landscape, macro, astrophotography
  "description": "תיאור טבעי ומקצועי של הפריים, ההתנהגות והאור (2-3 משפטים בעברית)",
  "description_en": "Professional and evocative description of the scene in English (2-3 sentences)",
  "humorous_description": "משפט משעשע, שנון והומוריסטי בגוף ראשון או מנקודת מבט הומוריסטית של בעל החיים",
  "humorous_description_en": "Witty, humorous English caption capturing the exact same comedic spirit",
  "tags": ["תגית1", "תגית2", "תגית3"],
  "tags_en": ["tag1", "tag2", "tag3"]
}

נתוני צילום נוספים לחילוץ הקשר:
מצלמה: ${exifData.camera || ''}, עדשה: ${exifData.lens || ''}, תאריך: ${exifData.date || ''}.`;

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{
        parts: [
          { text: prompt },
          {
            inline_data: {
              mime_type: 'image/webp',
              data: base64Data
            }
          }
        ]
      }],
      generationConfig: {
        response_mime_type: 'application/json'
      }
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini API error: ${response.status} - ${errText}`);
  }

  const result = await response.json();
  const rawJson = result.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!rawJson) throw new Error('No JSON output from Gemini');

  const parsed = JSON.parse(rawJson);

  // Cross-reference species with species_registry.json if possible
  if (parsed.species_latin && speciesRegistry[parsed.species_latin]) {
    const reg = speciesRegistry[parsed.species_latin];
    if (reg.he) parsed.species_hebrew = reg.he;
    if (reg.en) parsed.species_en = reg.en;
  }

  return parsed;
};

/**
 * Save new photo to Firestore (instantly visible on website)
 */
export const saveNewPhotoRecord = async (photoData, user) => {
  if (!db || !isUserOwner(user)) throw new Error('Only the owner can upload photos');

  const colRef = collection(db, 'custom_photos');
  const docRef = await addDoc(colRef, {
    ...photoData,
    uploaded_by: user.email,
    created_at: serverTimestamp()
  });

  return docRef.id;
};
