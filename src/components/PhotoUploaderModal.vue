<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import {
  extractExifFromFile,
  resizeImageToWebP,
  uploadBlobToR2,
  generatePhotoMetadataWithGemini,
  saveNewPhotoRecord,
  findExistingPhotoMatch,
  replacePhotoImage
} from '../utils/uploaderService.js';
import { getGeminiApiKey, saveGeminiApiKey } from '../utils/geminiCurator.js';
import { addPhotoToCuration } from '../utils/curationService.js';
import { logEvent, LOG_LEVELS, subscribeToSystemLogs } from '../utils/loggerService.js';
import { db } from '../utils/firebase.js';
import { collection, onSnapshot } from 'firebase/firestore';
import catalogPhotos from '../data/photos.json';

const props = defineProps({
  currentUser: {
    type: Object,
    required: true
  },
  currentLang: {
    type: String,
    default: 'he'
  }
});

const emit = defineEmits(['close', 'photo-uploaded']);

// Catalog & custom photos database for duplicate / match detection
const customPhotos = ref([]);
let unsubCustom = null;

const allPhotosList = computed(() => {
  return [...customPhotos.value, ...catalogPhotos];
});

// Multi-file upload queue
const uploadQueue = ref([]);
const selectedQueueIndex = ref(0);
const isBatchProcessing = ref(false);
const batchStepText = ref('');
const errorMessage = ref('');
const successMessage = ref('');
const fileInputRef = ref(null);

// Active photo item in the editor
const currentItem = computed(() => {
  if (uploadQueue.value.length === 0) return null;
  return uploadQueue.value[selectedQueueIndex.value] || uploadQueue.value[0];
});

// Live Firestore Logs
const liveLogs = ref([]);
const showLiveLogs = ref(false);
let unsubLogs = null;

// Gemini API Key management
const geminiApiKey = ref('');
const isKeyConfigured = ref(false);
const showKeyInput = ref(false);

const handleSaveKey = async () => {
  const key = geminiApiKey.value.trim();
  if (!key) return;
  await saveGeminiApiKey(key, props.currentUser);
  isKeyConfigured.value = true;
  showKeyInput.value = false;
  await logEvent(LOG_LEVELS.SUCCESS, 'auth', 'Gemini API key configured and saved');
};

onMounted(async () => {
  unsubLogs = subscribeToSystemLogs((logs) => {
    liveLogs.value = logs.slice(0, 8);
  }, 10);

  if (db) {
    unsubCustom = onSnapshot(collection(db, 'custom_photos'), (snap) => {
      const list = [];
      snap.forEach(d => list.push({ id: d.id, ...d.data() }));
      customPhotos.value = list;
    }, (err) => console.warn('Custom photos listener in uploader:', err));
  }

  const key = await getGeminiApiKey(props.currentUser);
  if (key) {
    geminiApiKey.value = key;
    isKeyConfigured.value = true;
  }
});

onUnmounted(() => {
  if (unsubLogs) unsubLogs();
  if (unsubCustom) unsubCustom();
  // Revoke object URLs
  uploadQueue.value.forEach(item => {
    if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
  });
});

// File Selection (Single or Multiple)
const handleFilesSelect = async (e) => {
  const files = Array.from(e.target.files || []);
  if (!files.length) return;

  errorMessage.value = '';
  successMessage.value = '';

  const newItems = files.map((file, idx) => ({
    id: `queue_${Date.now()}_${idx}`,
    file,
    name: file.name,
    size: (file.size / (1024 * 1024)).toFixed(2) + ' MB',
    previewUrl: URL.createObjectURL(file),
    status: 'pending', // 'pending' | 'processing' | 'matched' | 'ready' | 'published' | 'error'
    statusText: 'ממתין לעיבוד...',
    matchedPhoto: null,
    isReplacement: false,
    
    // Metadata
    photoId: `photo_${Date.now()}_${idx}`,
    titleHe: '',
    titleEn: '',
    speciesHe: '',
    speciesEn: '',
    speciesLa: '',
    category: 'wildlife',
    descHe: '',
    descEn: '',
    humorHe: '',
    humorEn: '',
    tagsHe: '',
    isFeatured: false,
    addToCurationExhibition: true,

    // Blobs & URLs
    displayBlob: null,
    thumbBlob: null,
    displayUrl: '',
    thumbUrl: '',
    dimensions: {},
    exif: {},
    isAiAnalyzing: false,
    errorMessage: ''
  }));

  const startIdx = uploadQueue.value.length;
  uploadQueue.value.push(...newItems);
  selectedQueueIndex.value = startIdx;

  if (e.target) e.target.value = '';

  // Process the queue items sequentially
  processQueue();
};

const processQueue = async () => {
  if (isBatchProcessing.value) return;
  isBatchProcessing.value = true;

  const key = geminiApiKey.value.trim() || (await getGeminiApiKey(props.currentUser));

  for (let i = 0; i < uploadQueue.value.length; i++) {
    const item = uploadQueue.value[i];
    if (item.status === 'published' || item.status === 'ready' || item.status === 'matched') {
      continue;
    }

    item.status = 'processing';
    item.statusText = 'מחלץ EXIF ובודק כפילויות...';
    batchStepText.value = `מעבד קובץ ${i + 1} מתוך ${uploadQueue.value.length}: ${item.name}...`;

    try {
      // 1. Extract EXIF
      const exifData = await extractExifFromFile(item.file);
      item.exif = exifData;

      // 2. Check for duplicate / existing version match
      const matched = findExistingPhotoMatch(item.file, exifData, allPhotosList.value);

      if (matched) {
        item.matchedPhoto = matched;
        item.isReplacement = true;
        item.status = 'matched';
        item.statusText = `זוהתה תמונה קיימת: ${matched.title || matched.id}`;

        // Pre-fill existing metadata
        item.titleHe = matched.title || matched.ai?.title || '';
        item.titleEn = matched.title_en || matched.ai?.title_en || '';
        item.speciesHe = matched.species_he || matched.ai?.species_hebrew || '';
        item.speciesEn = matched.species_en || matched.ai?.species_en || '';
        item.speciesLa = matched.species_la || matched.ai?.species_latin || '';
        item.category = matched.categoryKey || matched.category || matched.ai?.category || 'wildlife';
        item.descHe = matched.description || matched.ai?.description || '';
        item.descEn = matched.description_en || matched.ai?.description_en || '';
        item.humorHe = matched.humorous_description || matched.ai?.humorous_description || '';
        item.humorEn = matched.humorous_description_en || matched.ai?.humorous_description_en || '';
        item.tagsHe = (matched.tags || matched.ai?.tags || []).join(', ');
        item.isFeatured = Boolean(matched.is_featured);

        await logEvent(LOG_LEVELS.INFO, 'uploader', `Duplicate/version match detected for ${item.name} -> ${matched.id}`);
      } else {
        // Fallback clean title
        const cleanName = item.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
        item.titleHe = cleanName;

        // 3. Resize to WebP
        item.statusText = 'ממיר ל-WebP ברזולוציה גבוהה...';
        const displayWebP = await resizeImageToWebP(item.file, 2048, 0.88);
        const thumbWebP = await resizeImageToWebP(item.file, 600, 0.82);
        item.displayBlob = displayWebP.blob;
        item.thumbBlob = thumbWebP.blob;
        item.dimensions = {
          width: displayWebP.width,
          height: displayWebP.height,
          aspectRatio: displayWebP.aspectRatio
        };

        // 4. Run Gemini AI for new photo
        if (key) {
          item.statusText = 'מנתח באמצעות Gemini AI...';
          try {
            const aiData = await generatePhotoMetadataWithGemini(displayWebP.blob, exifData, key);
            item.titleHe = aiData.title || item.titleHe;
            item.titleEn = aiData.title_en || '';
            item.speciesHe = aiData.species_hebrew || '';
            item.speciesEn = aiData.species_en || '';
            item.speciesLa = aiData.species_latin || '';
            item.category = aiData.category || 'wildlife';
            item.descHe = aiData.description || '';
            item.descEn = aiData.description_en || '';
            item.humorHe = aiData.humorous_description || '';
            item.humorEn = aiData.humorous_description_en || '';
            item.tagsHe = (aiData.tags || []).join(', ');
          } catch (aiErr) {
            console.warn('Gemini tagging failed for queue item:', aiErr);
          }
        }

        item.status = 'ready';
        item.statusText = 'מוכן לפרסום';
      }
    } catch (err) {
      console.error(`Error processing ${item.name}:`, err);
      item.status = 'error';
      item.statusText = `שגיאה: ${err.message}`;
      item.errorMessage = err.message;
    }
  }

  isBatchProcessing.value = false;
  batchStepText.value = '';
};

// Re-run AI analysis on the currently selected item
const triggerAiAnalysisForItem = async (item) => {
  if (!item) return;
  const key = geminiApiKey.value.trim() || (await getGeminiApiKey(props.currentUser));
  if (!key) {
    showKeyInput.value = true;
    errorMessage.value = 'נא להזין מפתח Gemini כדי לבצע ניתוח AI.';
    return;
  }

  item.isAiAnalyzing = true;
  errorMessage.value = '';
  try {
    let blob = item.displayBlob;
    if (!blob) {
      const res = await resizeImageToWebP(item.file, 2048, 0.88);
      blob = res.blob;
      item.displayBlob = blob;
      item.thumbBlob = (await resizeImageToWebP(item.file, 600, 0.82)).blob;
    }

    const aiData = await generatePhotoMetadataWithGemini(blob, item.exif, key);
    item.titleHe = aiData.title || item.titleHe;
    item.titleEn = aiData.title_en || item.titleEn;
    item.speciesHe = aiData.species_hebrew || item.speciesHe;
    item.speciesEn = aiData.species_en || item.speciesEn;
    item.speciesLa = aiData.species_latin || item.speciesLa;
    item.category = aiData.category || item.category;
    item.descHe = aiData.description || item.descHe;
    item.descEn = aiData.description_en || item.descEn;
    item.humorHe = aiData.humorous_description || item.humorHe;
    item.humorEn = aiData.humorous_description_en || item.humorEn;
    item.tagsHe = (aiData.tags || []).join(', ');
    successMessage.value = `זיהוי ה-AI הושלם עבור ${item.name}!`;
    setTimeout(() => { successMessage.value = ''; }, 4000);
  } catch (err) {
    console.error('Manual AI error:', err);
    errorMessage.value = `שגיאה בניתוח AI: ${err.message}`;
  } finally {
    item.isAiAnalyzing = false;
  }
};

const removeItemFromQueue = (index) => {
  const removed = uploadQueue.value.splice(index, 1)[0];
  if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
  if (selectedQueueIndex.value >= uploadQueue.value.length) {
    selectedQueueIndex.value = Math.max(0, uploadQueue.value.length - 1);
  }
};

// Publish Single Item
const publishQueueItem = async (item) => {
  if (!item || item.status === 'published') return;

  item.status = 'processing';
  item.statusText = 'מעלה ל-R2 ומפרסם...';

  try {
    // 1. If it's a confirmed replacement of an existing photo:
    if (item.isReplacement && item.matchedPhoto) {
      await replacePhotoImage(item.matchedPhoto, item.file, props.currentUser);
      item.status = 'published';
      item.statusText = 'עודכן בהצלחה כגרסה חדשה!';
      return;
    }

    // 2. Otherwise publish as brand new photo:
    if (!item.displayBlob || !item.thumbBlob) {
      const disp = await resizeImageToWebP(item.file, 2048, 0.88);
      const th = await resizeImageToWebP(item.file, 600, 0.82);
      item.displayBlob = disp.blob;
      item.thumbBlob = th.blob;
      item.dimensions = { width: disp.width, height: disp.height, aspectRatio: disp.aspectRatio };
    }

    const now = new Date();
    const ts = now.toISOString().replace(/[-:T.Z]/g, '').slice(0, 14);
    const photoUniqueId = `photo_${ts}_${Math.floor(Math.random() * 1000)}`;

    const dispUrl = await uploadBlobToR2(item.displayBlob, `photos/display/${photoUniqueId}.webp`);
    const thUrl = await uploadBlobToR2(item.thumbBlob, `photos/thumbs/${photoUniqueId}.webp`);
    item.displayUrl = dispUrl;
    item.thumbUrl = thUrl;

    const rawTags = (item.tagsHe || '').split(',').map(t => t.trim()).filter(Boolean);

    const record = {
      id: photoUniqueId,
      filename: `${photoUniqueId}.jpg`,
      title: item.titleHe.trim() || 'תמונת טבע',
      title_en: item.titleEn.trim() || '',
      category: item.category,
      is_featured: item.isFeatured,
      display_url: dispUrl,
      thumb_url: thUrl,
      dimensions: item.dimensions,
      exif: item.exif,
      ai: {
        title: item.titleHe.trim(),
        title_en: item.titleEn.trim(),
        species_hebrew: item.speciesHe.trim(),
        species_latin: item.speciesLa.trim(),
        species_en: item.speciesEn.trim(),
        category: item.category,
        description: item.descHe.trim(),
        description_en: item.descEn.trim(),
        humorous_description: item.humorHe.trim(),
        humorous_description_en: item.humorEn.trim(),
        tags: rawTags,
        tags_en: []
      }
    };

    await saveNewPhotoRecord(record, props.currentUser);

    if (item.addToCurationExhibition) {
      await addPhotoToCuration({
        id: photoUniqueId,
        title: item.titleHe,
        title_en: item.titleEn,
        thumbnail: thUrl,
        display: dispUrl,
        species_he: item.speciesHe,
        species_en: item.speciesEn,
        category: item.category,
        exif: item.exif
      }, 'exhibition', 'pool');
    }

    item.status = 'published';
    item.statusText = 'פורסם בהצלחה!';
  } catch (err) {
    console.error('Failed to publish item:', err);
    item.status = 'error';
    item.statusText = `שגיאה בפרסום: ${err.message}`;
    throw err;
  }
};

// Publish All Ready & Matched Items in the Queue
const isPublishingAll = ref(false);
const publishAllProgressText = ref('');

const publishAllReadyItems = async () => {
  const readyItems = uploadQueue.value.filter(item => item.status === 'ready' || item.status === 'matched');
  if (!readyItems.length) return;

  isPublishingAll.value = true;
  errorMessage.value = '';
  successMessage.value = '';

  let successCount = 0;
  for (let i = 0; i < readyItems.length; i++) {
    const item = readyItems[i];
    publishAllProgressText.value = `מפרסם תמונה ${i + 1} מתוך ${readyItems.length}: ${item.name}...`;
    try {
      await publishQueueItem(item);
      successCount++;
    } catch (err) {
      console.warn(`Failed to publish ${item.name}:`, err);
    }
  }

  isPublishingAll.value = false;
  publishAllProgressText.value = '';

  if (successCount === readyItems.length) {
    successMessage.value = `כל ${successCount} התמונות פורסמו בהצלחה באתר!`;
    setTimeout(() => {
      emit('close');
    }, 2500);
  } else {
    errorMessage.value = `פורסמו ${successCount} מתוך ${readyItems.length} תמונות. בדוק שגיאות בתור.`;
  }
};

// Helper counts
const readyCount = computed(() => uploadQueue.value.filter(i => i.status === 'ready' || i.status === 'matched').length);
const publishedCount = computed(() => uploadQueue.value.filter(i => i.status === 'published').length);
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/85 backdrop-blur-md" dir="rtl">
    <div class="bg-slate-900 border border-slate-700 rounded-3xl max-w-4xl w-full max-h-[92vh] flex flex-col overflow-hidden shadow-2xl">
      
      <!-- Modal Header -->
      <header class="p-4 sm:p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
        <div class="flex items-center gap-2.5">
          <span class="text-2xl">📸</span>
          <div>
            <h3 class="font-bold text-sm sm:text-base text-white">סטודיו העלאת תמונות (Admin Studio)</h3>
            <p class="text-xs text-slate-400">זיהוי גרסאות קיים אוטומטי, העלאת קבצים מרובים ו-AI</p>
          </div>
        </div>
        <button @click="emit('close')" class="text-slate-400 hover:text-white p-1 cursor-pointer text-lg">✕</button>
      </header>

      <!-- Modal Body -->
      <div class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
        
        <!-- Gemini Key Banner -->
        <div class="p-3 bg-indigo-950/40 border border-indigo-500/30 rounded-2xl text-xs space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-bold text-indigo-300 flex items-center gap-1.5">
              <span>🤖</span>
              <span>אוצר הבינה המלאכותית (Gemini API)</span>
            </span>
            <button
              v-if="isKeyConfigured"
              type="button"
              @click="showKeyInput = !showKeyInput"
              class="text-indigo-400 hover:text-white text-[11px] underline cursor-pointer"
            >
              {{ showKeyInput ? 'הסתר' : 'ערוך מפתח' }}
            </button>
          </div>

          <div v-if="!isKeyConfigured || showKeyInput" class="space-y-2 pt-1 border-t border-indigo-500/20">
            <div class="flex items-center gap-2">
              <input
                v-model="geminiApiKey"
                type="password"
                placeholder="הדבק מפתח Gemini..."
                class="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-indigo-400"
              />
              <button
                type="button"
                @click="handleSaveKey"
                class="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-xl transition cursor-pointer shrink-0"
              >
                שמור
              </button>
            </div>
          </div>
          <div v-else class="text-[11px] text-emerald-400 font-medium flex items-center gap-1">
            <span>✓</span>
            <span>מחובר - מזהה אוטומטית מינים, כותרות, תיאורים והומור עבור תמונות חדשות</span>
          </div>
        </div>

        <!-- File Picker / Drop Zone (Always available to add more files) -->
        <div
          v-if="uploadQueue.length === 0"
          class="border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-2xl p-8 text-center cursor-pointer transition bg-slate-950/40"
        >
          <label class="cursor-pointer space-y-2 block">
            <span class="text-4xl block">📤</span>
            <span class="font-bold text-sm text-slate-200 block">בחר תמונות להעלאה (תומך בקובץ יחיד או בהרבה קבצים יחד)</span>
            <span class="text-xs text-slate-400 block">ניתן לבחור מספר תמונות יחד. המערכת תזהה אוטומטית תמונות קיימות, תחלץ EXIF ותפעיל AI.</span>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              class="hidden"
              @change="handleFilesSelect"
            />
          </label>
        </div>

        <!-- Queue Processing Progress -->
        <div v-if="isBatchProcessing || isPublishingAll" class="bg-sky-950/40 border border-sky-500/30 rounded-2xl p-4 flex items-center gap-3">
          <div class="w-5 h-5 rounded-full border-2 border-sky-400 border-t-transparent animate-spin shrink-0"></div>
          <span class="text-xs text-sky-200 font-medium truncate">{{ isPublishingAll ? publishAllProgressText : batchStepText }}</span>
        </div>

        <!-- Notification Banners -->
        <div v-if="errorMessage" class="bg-rose-950/60 border border-rose-600/40 text-rose-200 text-xs p-3 rounded-xl">
          ⚠️ {{ errorMessage }}
        </div>
        <div v-if="successMessage" class="bg-emerald-950/60 border border-emerald-600/40 text-emerald-200 text-xs p-3 rounded-xl font-bold text-center">
          ✓ {{ successMessage }}
        </div>

        <!-- Multi-File Queue Strip & Controls -->
        <div v-if="uploadQueue.length > 0" class="space-y-3">
          
          <div class="flex items-center justify-between bg-slate-950/80 p-3 rounded-2xl border border-slate-800">
            <div class="flex items-center gap-2">
              <span class="font-bold text-xs text-white">תור העלאה:</span>
              <span class="px-2 py-0.5 rounded-full bg-slate-800 text-[11px] font-mono text-sky-400">{{ uploadQueue.length }} תמונות</span>
              <span v-if="readyCount > 0" class="text-[11px] text-emerald-400 font-medium">({{ readyCount }} מוכנות לפרסום)</span>
            </div>

            <div class="flex items-center gap-2">
              <!-- Add more button -->
              <label class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer transition flex items-center gap-1.5">
                <span>➕</span>
                <span>הוסף עוד</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" multiple class="hidden" @change="handleFilesSelect" />
              </label>

              <!-- Publish All button -->
              <button
                v-if="readyCount > 1"
                type="button"
                @click="publishAllReadyItems"
                :disabled="isPublishingAll || isBatchProcessing"
                class="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs transition cursor-pointer flex items-center gap-1.5 shadow-lg shadow-emerald-900/30"
              >
                <span>🚀</span>
                <span>פרסם הכל ({{ readyCount }})</span>
              </button>
            </div>
          </div>

          <!-- Thumbnails Strip -->
          <div class="flex gap-2.5 overflow-x-auto pb-2 pt-1 scrollbar-thin">
            <div
              v-for="(item, idx) in uploadQueue"
              :key="item.id"
              @click="selectedQueueIndex = idx"
              class="relative w-20 sm:w-24 shrink-0 rounded-xl overflow-hidden border-2 cursor-pointer transition group"
              :class="selectedQueueIndex === idx ? 'border-sky-400 ring-2 ring-sky-500/30' : 'border-slate-800 hover:border-slate-600'"
            >
              <img :src="item.previewUrl" class="w-full h-16 sm:h-20 object-cover bg-slate-950" />
              
              <!-- Status Badge Overlay -->
              <div class="absolute top-1 right-1">
                <span v-if="item.status === 'matched'" class="px-1 py-0.2 rounded bg-amber-500 text-slate-950 font-bold text-[9px] shadow" title="זוהתה גרסה קיימת!">🔄</span>
                <span v-else-if="item.status === 'ready'" class="px-1 py-0.2 rounded bg-emerald-500 text-slate-950 font-bold text-[9px] shadow" title="מוכן">✓</span>
                <span v-else-if="item.status === 'processing'" class="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin block"></span>
                <span v-else-if="item.status === 'published'" class="px-1 py-0.2 rounded bg-sky-500 text-white font-bold text-[9px]">פורסם</span>
                <span v-else-if="item.status === 'error'" class="px-1 py-0.2 rounded bg-rose-500 text-white font-bold text-[9px]">⚠️</span>
              </div>

              <!-- Delete button from queue -->
              <button
                type="button"
                @click.stop="removeItemFromQueue(idx)"
                class="absolute top-1 left-1 opacity-0 group-hover:opacity-100 bg-rose-950/80 hover:bg-rose-600 text-white rounded-full w-4 h-4 text-[10px] flex items-center justify-center transition"
                title="הסר מתור"
              >✕</button>

              <div class="p-1 bg-slate-950/90 truncate text-[10px] text-slate-300">
                {{ item.titleHe || item.name }}
              </div>
            </div>
          </div>

        </div>

        <!-- Active Item Detailed Editor -->
        <div v-if="currentItem" class="space-y-4 pt-2 border-t border-slate-800">
          
          <!-- Matched Duplicate Alert Banner -->
          <div v-if="currentItem.matchedPhoto" class="bg-amber-950/40 border border-amber-500/50 p-4 rounded-2xl text-xs space-y-2">
            <div class="flex items-center gap-2 font-bold text-amber-300">
              <span class="text-base">💡</span>
              <span>זוהתה תמונה קיימת באתר!</span>
            </div>
            <p class="text-slate-300 leading-relaxed">
              הקובץ תואם לתמונה הקיימת <strong>"{{ currentItem.matchedPhoto.title || currentItem.matchedPhoto.id }}"</strong> (מזהה: <code class="font-mono text-amber-200">{{ currentItem.matchedPhoto.id }}</code>).
              הפרטים הקיימים נטענו אוטומטית. פרסום תמונה זו ישמור אותה כגרסה מעודכנת של התמונה תוך <strong>שמירת כל הלייקים והתגובות</strong>, ושמירת הגרסה הקודמת בהיסטוריה!
            </p>
            <div class="flex items-center gap-3 pt-1">
              <label class="flex items-center gap-2 cursor-pointer font-semibold text-amber-200">
                <input type="checkbox" v-model="currentItem.isReplacement" class="rounded text-amber-500" />
                <span>החלף ושמור כגרסה חדשה של תמונה זו (מומלץ)</span>
              </label>
            </div>
          </div>

          <!-- Photo Preview & EXIF Summary -->
          <div class="flex items-start gap-4 p-3 bg-slate-950 rounded-xl border border-slate-800">
            <img :src="currentItem.previewUrl" class="w-24 h-24 object-cover rounded-lg shrink-0 border border-slate-700" />
            <div class="text-xs space-y-1 text-slate-300 flex-1 min-w-0">
              <p class="truncate"><strong class="text-white">קובץ:</strong> {{ currentItem.name }} ({{ currentItem.size }})</p>
              <p><strong class="text-white">מצלמה:</strong> {{ currentItem.exif.camera || 'לא זוהה' }}</p>
              <p><strong class="text-white">עדשה:</strong> {{ currentItem.exif.lens || 'לא צוין' }}</p>
              <p><strong class="text-white">חשיפה:</strong> {{ currentItem.exif.aperture || '—' }} • {{ currentItem.exif.shutterSpeed || '—' }} • ISO {{ currentItem.exif.iso || '—' }}</p>
            </div>
          </div>

          <!-- Manual AI Trigger for Current Item -->
          <div class="flex items-center justify-between bg-indigo-950/40 p-3 rounded-xl border border-indigo-500/40">
            <div>
              <span class="text-xs font-bold text-indigo-200 block">זיהוי וניתוח AI (Gemini) עבור תמונה זו</span>
              <span class="text-[11px] text-slate-400 block">ממלא אוטומטית שמות מינים בעברית ובאנגלית, תיאורים והומור</span>
            </div>
            <button
              type="button"
              @click="triggerAiAnalysisForItem(currentItem)"
              :disabled="currentItem.isAiAnalyzing"
              class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-xs transition cursor-pointer flex items-center gap-2 shadow-md shrink-0"
            >
              <span v-if="currentItem.isAiAnalyzing" class="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin"></span>
              <span v-else>✨</span>
              <span>{{ currentItem.isAiAnalyzing ? 'ג\'ימיני מנתח...' : 'הפעל זיהוי AI כעת' }}</span>
            </button>
          </div>

          <!-- Bilingual Titles -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">כותרת (עברית):</label>
              <input v-model="currentItem.titleHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">Title (English):</label>
              <input v-model="currentItem.titleEn" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
          </div>

          <!-- Species Names -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">שם המין (עברית):</label>
              <input v-model="currentItem.speciesHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">שם לטיני מדעי:</label>
              <input v-model="currentItem.speciesLa" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white italic" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">English Species Name:</label>
              <input v-model="currentItem.speciesEn" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
          </div>

          <!-- Category -->
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">קטגוריה:</label>
            <select v-model="currentItem.category" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white">
              <option value="wildlife">טבע וציפורים (Wildlife)</option>
              <option value="landscape">נוף (Landscape)</option>
              <option value="macro">מאקרו (Macro)</option>
              <option value="astrophotography">אסטרופוטוגרפיה (Astrophotography)</option>
            </select>
          </div>

          <!-- Descriptions -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">תיאור (עברית):</label>
              <textarea v-model="currentItem.descHe" rows="2" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white"></textarea>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">Description (English):</label>
              <textarea v-model="currentItem.descEn" rows="2" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white"></textarea>
            </div>
          </div>

          <!-- Humorous Descriptions -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-amber-950/20 p-3 rounded-xl border border-amber-500/20">
            <div>
              <label class="block text-xs font-semibold text-amber-300 mb-1">🎭 משפט הומוריסטי (עברית):</label>
              <input v-model="currentItem.humorHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-amber-100" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-amber-300 mb-1">🎭 Witty Caption (English):</label>
              <input v-model="currentItem.humorEn" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-amber-100" />
            </div>
          </div>

          <!-- Tags -->
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">תגיות (מופרדות בפסיקים):</label>
            <input v-model="currentItem.tagsHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
          </div>

          <!-- Checkboxes -->
          <div class="flex items-center gap-6 pt-1 text-xs">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="currentItem.isFeatured" class="rounded text-amber-500" />
              <span>⭐ סמן כתמונה נבחרת (Featured)</span>
            </label>

            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="currentItem.addToCurationExhibition" class="rounded text-indigo-500" />
              <span>🎨 הוסף מיד למאגר התערוכה</span>
            </label>
          </div>

          <!-- Individual item publish button -->
          <div class="flex justify-end pt-2">
            <button
              type="button"
              @click="publishQueueItem(currentItem)"
              :disabled="currentItem.status === 'published' || isPublishingAll"
              class="px-5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 cursor-pointer"
              :class="currentItem.status === 'published' ? 'bg-slate-800 text-slate-500 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg'"
            >
              <span>{{ currentItem.status === 'published' ? '✓ פורסם' : (currentItem.isReplacement ? '🔄 פרסם כגרסה מעודכנת' : '🚀 פרסם תמונה זו') }}</span>
            </button>
          </div>

        </div>

        <!-- Live System Logs Accordion -->
        <div class="border border-slate-800 rounded-xl bg-slate-950/60 overflow-hidden text-xs">
          <button
            type="button"
            @click="showLiveLogs = !showLiveLogs"
            class="w-full px-3.5 py-2 flex items-center justify-between text-slate-400 hover:text-slate-200 cursor-pointer bg-slate-950/80 transition"
          >
            <span class="flex items-center gap-2 font-mono">
              <span>📜 לוגים חיים (Firebase)</span>
              <span class="px-1.5 py-0.2 bg-slate-800 rounded text-[10px] text-sky-400">{{ liveLogs.length }}</span>
            </span>
            <span class="text-[10px] text-slate-500">{{ showLiveLogs ? 'הסתר ▲' : 'הצג ▼' }}</span>
          </button>

          <div v-if="showLiveLogs" class="p-3 space-y-1.5 max-h-36 overflow-y-auto font-mono text-[11px] border-t border-slate-800/80">
            <div
              v-for="log in liveLogs"
              :key="log.id"
              class="flex items-start gap-2 leading-tight py-0.5 border-b border-slate-900/60"
              :class="log.level === 'error' ? 'text-rose-400' : (log.level === 'warn' ? 'text-amber-300' : (log.level === 'success' ? 'text-emerald-400' : 'text-slate-300'))"
            >
              <span class="text-[10px] text-slate-500 shrink-0">[{{ log.client_time }}]</span>
              <span class="shrink-0 uppercase text-[9px] px-1 rounded font-bold" :class="log.level === 'error' ? 'bg-rose-950 border border-rose-800' : (log.level === 'success' ? 'bg-emerald-950 border border-emerald-800' : 'bg-slate-800')">{{ log.category }}</span>
              <span class="truncate flex-1">{{ log.message }}</span>
            </div>
            <div v-if="liveLogs.length === 0" class="text-slate-500 italic">אין עדיין לוגים במערכת</div>
          </div>
        </div>

      </div>

      <!-- Modal Footer -->
      <footer class="p-4 border-t border-slate-800 flex items-center justify-between bg-slate-950/40">
        <button @click="emit('close')" class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer">סגור</button>
        <div class="flex items-center gap-2">
          <button
            v-if="readyCount > 0"
            @click="publishAllReadyItems"
            :disabled="isPublishingAll || isBatchProcessing"
            class="px-6 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs transition cursor-pointer shadow-lg flex items-center gap-2"
          >
            <span>🚀</span>
            <span>{{ readyCount === 1 ? 'פרסם תמונה לאתר' : `פרסם את כל ${readyCount} התמונות` }}</span>
          </button>
        </div>
      </footer>

    </div>
  </div>
</template>
