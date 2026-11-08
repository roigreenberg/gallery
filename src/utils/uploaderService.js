// uploaderService.js - Client-Side Owner Photo Processing & Cloudflare R2 Upload Pipeline
import exifr from 'exifr';
import { auth, db, isUserOwner } from './firebase.js';
import { collection, addDoc, doc, setDoc, updateDoc, deleteDoc, onSnapshot, serverTimestamp } from 'firebase/firestore';
import speciesRegistry from '../data/species_registry.json';
import { logEvent, LOG_LEVELS } from './loggerService.js';

export const R2_CONFIG = {
  workerUrl: 'https://gallery-uploader.roigreenberg.workers.dev',
  publicUrl: 'https://pub-d8a9140bbd28466cb778bf724fb793b0.r2.dev'
};

/**
 * Extract EXIF metadata from raw File
 */
export const extractExifFromFile = async (file) => {
  try {
    const rawExif = await exifr.parse(file, { tiff: true, xmp: true, exif: true });

    if (!rawExif) {
      await logEvent(LOG_LEVELS.WARN, 'exif', `No EXIF metadata found in file: ${file.name}`);
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

    // Format shutter speed (e.g., 1/1600s or 0.5s)
    let shutterStr = '';
    const expTime = rawExif.ExposureTime || (rawExif.ShutterSpeedValue ? 1 / Math.pow(2, rawExif.ShutterSpeedValue) : null);
    if (expTime) {
      if (expTime < 1) {
        shutterStr = `1/${Math.round(1 / expTime)}s`;
      } else {
        shutterStr = `${expTime}s`;
      }
    }

    const rawAperture = rawExif.FNumber || (rawExif.ApertureValue ? Math.pow(2, rawExif.ApertureValue / 2) : null);
    const apertureStr = rawAperture ? `f/${Number(rawAperture).toFixed(1).replace(/\.0$/, '')}` : '';
    const focalStr = rawExif.FocalLength ? `${Math.round(rawExif.FocalLength)}mm` : '';
    
    const make = (rawExif.Make || '').trim();
    let model = (rawExif.Model || '').trim();
    let cameraStr = model;
    if (make && !model.toLowerCase().includes(make.toLowerCase())) {
      cameraStr = `${make} ${model}`.trim();
    }
    if (!cameraStr) cameraStr = make || 'לא ידוע';

    const lensStr = rawExif.LensModel || rawExif.Lens || rawExif.LensType || 'לא צוין';
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

    await logEvent(LOG_LEVELS.INFO, 'exif', `EXIF parsed successfully from ${file.name}`, {
      camera: cameraStr,
      lens: lensStr,
      aperture: apertureStr,
      shutter: shutterStr,
      iso: isoStr
    });

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
 * Upload WebP Blob securely to Cloudflare R2 via authenticated Cloudflare Worker proxy
 */
export const uploadBlobToR2 = async (blob, objectKey) => {
  const cleanKey = objectKey.replace(/^\//, '');

  if (!auth?.currentUser) {
    throw new Error('יש להתחבר עם חשבון מנהל (Google) על מנת להעלות תמונות לגלריה');
  }

  try {
    const idToken = await auth.currentUser.getIdToken();

    const response = await fetch(`${R2_CONFIG.workerUrl}?key=${encodeURIComponent(cleanKey)}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${idToken}`,
        'Content-Type': 'image/webp'
      },
      body: blob
    });

    if (!response.ok) {
      let errMsg = `Upload failed with status ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData.error) errMsg = errorData.error;
      } catch (e) {}
      throw new Error(errMsg);
    }

    const data = await response.json();
    const publicUrl = data.url || `${R2_CONFIG.publicUrl}/${cleanKey}`;
    await logEvent(LOG_LEVELS.SUCCESS, 'r2', `Uploaded to R2 via Worker: ${cleanKey}`, { publicUrl });
    return publicUrl;
  } catch (err) {
    console.error(`Worker upload error for ${cleanKey}:`, err);
    await logEvent(LOG_LEVELS.ERROR, 'r2', `Worker upload failed for ${cleanKey}`, { error: err.message });
    throw err;
  }
};

/**
 * Analyze image and generate bilingual metadata using Gemini AI via secure Worker proxy
 */
export const generatePhotoMetadataWithGemini = async (imageDisplayBlob, exifData, _optionalKey = '') => {
  if (!auth?.currentUser) {
    throw new Error('יש להתחבר עם חשבון מנהל (Google) על מנת להשתמש ב-AI');
  }

  // Convert blob to base64
  const base64Data = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64 = reader.result.split(',')[1];
      resolve(base64);
    };
    reader.readAsDataURL(imageDisplayBlob);
  });

  const idToken = await auth.currentUser.getIdToken();

  await logEvent(LOG_LEVELS.INFO, 'ai', 'Sending photo to Cloudflare Worker for Gemini AI analysis...', {
    camera: exifData?.camera,
    lens: exifData?.lens
  });

  const response = await fetch(`${R2_CONFIG.workerUrl}/analyze`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      base64Data,
      exifData
    })
  });

  if (!response.ok) {
    let errText = `Status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.error) errText = errJson.error;
    } catch (e) {
      errText = await response.text();
    }
    await logEvent(LOG_LEVELS.ERROR, 'ai', `Worker AI analysis returned error`, { error: errText });
    throw new Error(`AI error: ${errText}`);
  }

  const parsed = await response.json();

  // Cross-reference species with species_registry.json if possible
  if (parsed.species_latin) {
    const latKey = parsed.species_latin.trim().toLowerCase();
    const reg = speciesRegistry.by_latin?.[latKey];
    if (reg) {
      if (reg.hebrew) parsed.species_hebrew = reg.hebrew;
      if (reg.english) parsed.species_en = reg.english;
      if (reg.latin) parsed.species_latin = reg.latin;
    }
  }

  await logEvent(LOG_LEVELS.SUCCESS, 'ai', `Gemini AI analysis complete: ${parsed.title || ''}`, {
    species: parsed.species_hebrew || '',
    category: parsed.category || ''
  });

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

  await logEvent(LOG_LEVELS.SUCCESS, 'firestore', `Saved new photo to Firestore: ${photoData.title || docRef.id}`, {
    id: docRef.id,
    photo_id: photoData.id
  });

  return docRef.id;
};

/**
 * Extract photo signature from filename and EXIF date
 */
export const extractPhotoSignature = (filename, exifDateStr) => {
  const clean = (filename || '').replace(/\.[^/.]+$/, '').trim();

  // 1. Camera pattern: e.g. RG5_4584, RG7_1437, RG5-1234
  const camMatch = clean.match(/(RG\d*[-_]\d{4,5})/i);
  // 2. Phone pattern: e.g. 20261005_182529 or 20261005-182529
  const phoneMatch = clean.match(/(\d{8}[-_]\d{6})/);
  // 3. Generic camera code: e.g. DSC_1234, IMG_1234
  const genMatch = clean.match(/([A-Z]{2,4}[-_]\d{3,5})/i);

  let baseToken = '';
  if (camMatch) {
    baseToken = camMatch[1].replace('-', '_').toUpperCase();
  } else if (phoneMatch) {
    baseToken = phoneMatch[1].replace('-', '_');
  } else if (genMatch) {
    baseToken = genMatch[1].replace('-', '_').toUpperCase();
  } else {
    baseToken = clean.toLowerCase();
  }

  // Extract date (YYYYMMDD) and time (HHMM)
  let datePart = '';
  let timePart = '';
  if (exifDateStr && typeof exifDateStr === 'string') {
    const m = exifDateStr.match(/^(\d{4})[:\-](\d{2})[:\-](\d{2})\s*(\d{2})?[:\-]?(\d{2})?/);
    if (m) {
      datePart = `${m[1]}${m[2]}${m[3]}`;
      timePart = m[4] && m[5] ? `${m[4]}${m[5]}` : '';
    }
  }

  if (!datePart) {
    const dm = clean.match(/^(\d{8})/);
    if (dm) datePart = dm[1];
  }

  return { baseToken, datePart, timePart, clean };
};

/**
 * Check if an uploaded file matches an existing photo in the gallery
 */
export const findExistingPhotoMatch = (file, exifData, catalogPhotos) => {
  if (!catalogPhotos || !catalogPhotos.length) return null;

  const newSig = extractPhotoSignature(file.name, exifData?.date_time_original || exifData?.date);

  for (const p of catalogPhotos) {
    const pId = p.id || '';
    const pDate = p.exif?.date_time_original || p.exif?.date || '';
    const pSig = extractPhotoSignature(pId, pDate);

    // Exact ID match (case-insensitive)
    if (pId.toLowerCase() === newSig.clean.toLowerCase()) {
      return p;
    }

    // Camera/Phone base token match (e.g. both RG5_4584)
    if (newSig.baseToken && pSig.baseToken && newSig.baseToken === pSig.baseToken) {
      if (newSig.datePart && pSig.datePart) {
        if (newSig.datePart === pSig.datePart) {
          // If both have timePart (HHMM), check if within same hour or close
          if (newSig.timePart && pSig.timePart) {
            const diff = Math.abs(parseInt(newSig.timePart, 10) - parseInt(pSig.timePart, 10));
            if (diff <= 30 || newSig.timePart.slice(0, 2) === pSig.timePart.slice(0, 2)) {
              return p;
            }
          } else {
            return p;
          }
        }
      } else {
        return p;
      }
    }
  }

  return null;
};

/**
 * Replace the image file of an existing photo (preserving all metadata, likes, comments & ID, and archiving history)
 */
export const replacePhotoImage = async (photo, newFile, user) => {
  if (!db || !isUserOwner(user)) throw new Error('Only the site owner can replace photos');

  await logEvent(LOG_LEVELS.INFO, 'replace', `Starting photo image replacement for: ${photo.id}`);

  // 1. Generate new high-res & thumb WebP files
  const displayWebP = await resizeImageToWebP(newFile, 2048, 0.88);
  const thumbWebP = await resizeImageToWebP(newFile, 600, 0.82);

  // 2. Upload to Cloudflare R2 with cache-busting timestamp
  const versionTs = Date.now();
  const displayKey = `photos/display/${photo.id}_v${versionTs}.webp`;
  const thumbKey = `photos/thumbs/${photo.id}_v${versionTs}.webp`;

  const newDisplayUrl = await uploadBlobToR2(displayWebP.blob, displayKey);
  const newThumbUrl = await uploadBlobToR2(thumbWebP.blob, thumbKey);

  // 3. Extract new EXIF if available from the new file
  let newExif = null;
  try {
    newExif = await extractExifFromFile(newFile);
  } catch (e) {
    console.warn('Could not extract EXIF from replacement file:', e);
  }

  // 4. Build version history
  const existingVersions = Array.isArray(photo.versions) && photo.versions.length > 0 
    ? [...photo.versions] 
    : [
        {
          version_id: 'v_original',
          display_url: photo.display || photo.display_url || '',
          thumb_url: photo.thumbnail || photo.thumb_url || '',
          width: photo.width || 2048,
          height: photo.height || 1366,
          aspect_ratio: photo.aspectRatio || '3/2',
          created_at: 'מקורית',
          label: 'גרסה מקורית'
        }
      ];

  const newVersionId = `v_${versionTs}`;
  const newVersionObj = {
    version_id: newVersionId,
    display_url: newDisplayUrl,
    thumb_url: newThumbUrl,
    width: displayWebP.width,
    height: displayWebP.height,
    aspect_ratio: displayWebP.aspectRatio,
    created_at: new Date().toLocaleDateString('he-IL') + ' ' + new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }),
    filename: newFile.name,
    label: `גרסה ${existingVersions.length + 1}`
  };

  const updatedVersions = [...existingVersions, newVersionObj];

  const updatePayload = {
    display_url: newDisplayUrl,
    thumb_url: newThumbUrl,
    width: displayWebP.width,
    height: displayWebP.height,
    aspect_ratio: displayWebP.aspectRatio,
    versions: updatedVersions,
    active_version_id: newVersionId,
    updated_at: serverTimestamp()
  };

  if (newExif && newExif.camera && newExif.camera !== 'לא ידוע') {
    updatePayload.exif = newExif;
  }

  // 5. Update in Firestore
  if (photo.is_custom || photo.firestore_id) {
    const docId = photo.firestore_id || photo.id;
    await updateDoc(doc(db, 'custom_photos', docId), updatePayload);
  } else {
    // Static catalog photo override
    await setDoc(doc(db, 'photo_overrides', photo.id), updatePayload, { merge: true });
  }

  await logEvent(LOG_LEVELS.SUCCESS, 'replace', `Photo image replaced successfully: ${photo.id}`, {
    displayUrl: newDisplayUrl,
    versionId: newVersionId
  });

  return {
    displayUrl: newDisplayUrl,
    thumbUrl: newThumbUrl,
    width: displayWebP.width,
    height: displayWebP.height,
    aspectRatio: displayWebP.aspectRatio,
    versions: updatedVersions,
    activeVersionId: newVersionId,
    exif: newExif || photo.exif
  };
};

/**
 * Switch which version of a photo is displayed on the website
 */
export const switchPhotoVersion = async (photo, targetVersionId, user) => {
  if (!db || !isUserOwner(user)) throw new Error('Only the owner can switch photo versions');

  const targetVersion = (photo.versions || []).find(v => v.version_id === targetVersionId);
  if (!targetVersion) throw new Error('Target version not found');

  const updatePayload = {
    active_version_id: targetVersionId,
    display_url: targetVersion.display_url,
    thumb_url: targetVersion.thumb_url,
    width: targetVersion.width || photo.width,
    height: targetVersion.height || photo.height,
    aspect_ratio: targetVersion.aspect_ratio || photo.aspectRatio,
    updated_at: serverTimestamp()
  };

  if (photo.is_custom || photo.firestore_id) {
    const docId = photo.firestore_id || photo.id;
    await updateDoc(doc(db, 'custom_photos', docId), updatePayload);
  } else {
    await setDoc(doc(db, 'photo_overrides', photo.id), updatePayload, { merge: true });
  }

  await logEvent(LOG_LEVELS.INFO, 'version', `Switched photo ${photo.id} to version ${targetVersionId}`);

  return targetVersion;
};

/**
 * Permanently delete a photo from the gallery (requires owner confirmation)
 */
export const deletePhotoPermanently = async (photo, user) => {
  if (!db || !isUserOwner(user)) throw new Error('Only the site owner can delete photos');

  await logEvent(LOG_LEVELS.WARN, 'delete', `Deleting photo: ${photo.id}`);

  if (photo.is_custom || photo.firestore_id) {
    const docId = photo.firestore_id || photo.id;
    await deleteDoc(doc(db, 'custom_photos', docId));
  } else {
    await setDoc(doc(db, 'photo_overrides', photo.id), {
      deleted: true,
      deleted_at: serverTimestamp()
    }, { merge: true });
  }

  await logEvent(LOG_LEVELS.SUCCESS, 'delete', `Photo deleted successfully: ${photo.id}`);
  return true;
};

/**
 * Real-time listener for photo overrides (replaced images or deleted photos)
 */
export const subscribeToPhotoOverrides = (callback) => {
  if (!db) {
    callback({});
    return () => {};
  }
  return onSnapshot(collection(db, 'photo_overrides'), (snapshot) => {
    const overrides = {};
    snapshot.forEach((docSnap) => {
      overrides[docSnap.id] = docSnap.data();
    });
    callback(overrides);
  }, (err) => {
    console.warn('photo_overrides listener error:', err);
  });
};
