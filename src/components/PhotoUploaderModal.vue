<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import {
  extractExifFromFile,
  resizeImageToWebP,
  uploadBlobToR2,
  generatePhotoMetadataWithGemini,
  saveNewPhotoRecord
} from '../utils/uploaderService.js';
import { getGeminiApiKey } from '../utils/geminiCurator.js';
import { addPhotoToCuration } from '../utils/curationService.js';
import { logEvent, LOG_LEVELS, subscribeToSystemLogs } from '../utils/loggerService.js';

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

// State
const selectedFile = ref(null);
const previewUrl = ref('');
const isProcessing = ref(false);
const processingStep = ref('');
const errorMessage = ref('');
const successMessage = ref('');

// Form Data (populated by EXIF + Gemini)
const photoId = ref('');
const titleHe = ref('');
const titleEn = ref('');
const speciesHe = ref('');
const speciesEn = ref('');
const speciesLa = ref('');
const category = ref('wildlife');
const descHe = ref('');
const descEn = ref('');
const humorHe = ref('');
const humorEn = ref('');
const tagsHe = ref('');
const isFeatured = ref(false);
const addToCurationExhibition = ref(true);

const displayUrl = ref('');
const thumbUrl = ref('');
const extractedExif = ref({});
const dimensions = ref({});

// Live Firestore Logs
const liveLogs = ref([]);
const showLiveLogs = ref(false);
let unsubLogs = null;

onMounted(() => {
  unsubLogs = subscribeToSystemLogs((logs) => {
    liveLogs.value = logs.slice(0, 8);
  }, 10);
});

onUnmounted(() => {
  if (unsubLogs) unsubLogs();
});

const handleFileSelect = async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;

  selectedFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  errorMessage.value = '';
  isProcessing.value = true;

  try {
    // 1. Generate unique photo ID based on timestamp
    const now = new Date();
    const ts = now.toISOString().replace(/[-:T.Z]/g, '').slice(0, 14);
    photoId.value = `photo_${ts}`;

    // 2. Extract EXIF
    processingStep.value = 'מחלץ נתוני מצלמה ועדשה (EXIF)...';
    const exifData = await extractExifFromFile(file);
    extractedExif.value = exifData;

    // 3. Resize to WebP
    processingStep.value = 'ממיר ל-WebP ברזולוציה גבוהה (2048px) וממוזערת (600px)...';
    const displayWebP = await resizeImageToWebP(file, 2048, 0.88);
    const thumbWebP = await resizeImageToWebP(file, 600, 0.82);
    dimensions.value = {
      width: displayWebP.width,
      height: displayWebP.height,
      aspectRatio: displayWebP.aspectRatio
    };

    // 4. Upload to Cloudflare R2
    processingStep.value = 'מעלה קבצים ישירות ל-Cloudflare R2...';
    const dispUrl = await uploadBlobToR2(displayWebP.blob, `photos/display/${photoId.value}.webp`);
    const thUrl = await uploadBlobToR2(thumbWebP.blob, `photos/thumbs/${photoId.value}.webp`);
    displayUrl.value = dispUrl;
    thumbUrl.value = thUrl;

    // 5. Generate metadata via Gemini API
    processingStep.value = 'מנתח תמונה באמצעות Gemini (זיהוי מין, כותרות, תיאורים והומור בעברית ובאנגלית)...';
    const apiKey = (await getGeminiApiKey(props.currentUser)) || 
      (typeof import.meta !== 'undefined' ? import.meta.env?.PUBLIC_GEMINI_API_KEY : '');

    if (apiKey) {
      try {
        const aiData = await generatePhotoMetadataWithGemini(displayWebP.blob, exifData, apiKey);
        titleHe.value = aiData.title || '';
        titleEn.value = aiData.title_en || '';
        speciesHe.value = aiData.species_hebrew || '';
        speciesEn.value = aiData.species_en || '';
        speciesLa.value = aiData.species_latin || '';
        category.value = aiData.category || 'wildlife';
        descHe.value = aiData.description || '';
        descEn.value = aiData.description_en || '';
        humorHe.value = aiData.humorous_description || '';
        humorEn.value = aiData.humorous_description_en || '';
        tagsHe.value = (aiData.tags || []).join(', ');
      } catch (aiErr) {
        console.warn('Gemini metadata generation failed:', aiErr);
        await logEvent(LOG_LEVELS.WARN, 'uploader', `Gemini tagging error: ${aiErr.message}`);
        errorMessage.value = `שימו לב: ניתוח ה-AI החזיר שגיאה (${aiErr.message}), אך התמונה הועלתה בהצלחה ל-R2! באפשרותך לערוך את הפרטים ידנית.`;
      }
    } else {
      await logEvent(LOG_LEVELS.WARN, 'uploader', 'No Gemini API key found for tagging');
    }

    // Fallback title if AI was empty
    const cleanFileName = file.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
    if (!titleHe.value) {
      titleHe.value = cleanFileName;
    }

    processingStep.value = 'הניתוח הושלם! בדוק את הנתונים ולחץ "פרסם".';
    await logEvent(LOG_LEVELS.INFO, 'uploader', `Photo preprocessed ready for publish: ${photoId.value}`, {
      fileName: file.name,
      camera: exifData.camera
    });
  } catch (err) {
    console.error('Processing error:', err);
    errorMessage.value = `שגיאה בעיבוד התמונה: ${err.message}`;
  } finally {
    isProcessing.value = false;
  }
};

const handlePublish = async () => {
  if (!displayUrl.value || !thumbUrl.value) return;
  isProcessing.value = true;
  processingStep.value = 'שומר ומפרסם באתר...';

  try {
    const rawTags = tagsHe.value.split(',').map(t => t.trim()).filter(Boolean);

    const record = {
      id: photoId.value,
      filename: `${photoId.value}.jpg`,
      title: titleHe.value.trim() || 'תמונת טבע',
      title_en: titleEn.value.trim() || '',
      category: category.value,
      is_featured: isFeatured.value,
      display_url: displayUrl.value,
      thumb_url: thumbUrl.value,
      dimensions: dimensions.value,
      exif: extractedExif.value,
      ai: {
        title: titleHe.value.trim(),
        title_en: titleEn.value.trim(),
        species_hebrew: speciesHe.value.trim(),
        species_latin: speciesLa.value.trim(),
        species_en: speciesEn.value.trim(),
        category: category.value,
        description: descHe.value.trim(),
        description_en: descEn.value.trim(),
        humorous_description: humorHe.value.trim(),
        humorous_description_en: humorEn.value.trim(),
        tags: rawTags,
        tags_en: []
      }
    };

    // Save to Firestore
    await saveNewPhotoRecord(record, props.currentUser);

    // If requested, also add to Exhibition Curation
    if (addToCurationExhibition.value) {
      await addPhotoToCuration({
        id: photoId.value,
        title: titleHe.value,
        title_en: titleEn.value,
        thumbnail: thumbUrl.value,
        display: displayUrl.value,
        species_he: speciesHe.value,
        species_en: speciesEn.value,
        category: category.value,
        exif: extractedExif.value
      }, 'exhibition', 'pool');
    }

    successMessage.value = 'התמונה פורסמה בהצלחה ומופיעה כעת באתר!';
    setTimeout(() => {
      emit('photo-uploaded', record);
      emit('close');
    }, 2000);
  } catch (err) {
    console.error('Publish error:', err);
    errorMessage.value = `שגיאה בשמירה: ${err.message}`;
  } finally {
    isProcessing.value = false;
  }
};
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md" dir="rtl">
    <div class="bg-slate-900 border border-slate-700 rounded-3xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl">
      
      <!-- Modal Header -->
      <header class="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
        <div class="flex items-center gap-2.5">
          <span class="text-2xl">📸</span>
          <div>
            <h3 class="font-bold text-base text-white">העלאת תמונה חדשה (Admin Studio)</h3>
            <p class="text-xs text-slate-400">חילוץ EXIF אוטומטי, המרה ל-WebP וניתוח דו-לשוני של ג'ימיני</p>
          </div>
        </div>
        <button @click="emit('close')" class="text-slate-400 hover:text-white p-1 cursor-pointer">✕</button>
      </header>

      <!-- Modal Body -->
      <div class="flex-1 overflow-y-auto p-6 space-y-6">
        
        <!-- File Picker -->
        <div v-if="!selectedFile" class="border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-2xl p-8 text-center cursor-pointer transition bg-slate-950/40">
          <label class="cursor-pointer space-y-2 block">
            <span class="text-4xl block">📤</span>
            <span class="font-bold text-sm text-slate-200 block">גרור לכאן תמונת JPG מקורית, או לחץ לבחירת קובץ</span>
            <span class="text-xs text-slate-500 block">הדפדפן יחלץ אוטומטית EXIF, ימיר ל-WebP ויבצע ניתוח AI</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="handleFileSelect" />
          </label>
        </div>

        <!-- Processing Progress Spinner -->
        <div v-if="isProcessing" class="bg-sky-950/40 border border-sky-500/30 rounded-2xl p-5 text-center space-y-3">
          <div class="w-8 h-8 rounded-full border-2 border-sky-400 border-t-transparent animate-spin mx-auto"></div>
          <p class="text-xs sm:text-sm text-sky-200 font-medium">{{ processingStep }}</p>
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

        <!-- Error & Success Banners -->
        <div v-if="errorMessage" class="bg-rose-950/60 border border-rose-600/40 text-rose-200 text-xs p-3 rounded-xl">
          ⚠️ {{ errorMessage }}
        </div>
        <div v-if="successMessage" class="bg-emerald-950/60 border border-emerald-600/40 text-emerald-200 text-xs p-3 rounded-xl font-bold text-center">
          ✓ {{ successMessage }}
        </div>

        <!-- Review & Edit Metadata Form (Once file is processed) -->
        <div v-if="selectedFile && !isProcessing" class="space-y-4">
          <div class="flex items-start gap-4 p-3 bg-slate-950 rounded-xl border border-slate-800">
            <img :src="previewUrl" class="w-24 h-24 object-cover rounded-lg shrink-0 border border-slate-700" />
            <div class="text-xs space-y-1 text-slate-300">
              <p><strong class="text-white">קובץ:</strong> {{ selectedFile.name }}</p>
              <p><strong class="text-white">מצלמה:</strong> {{ extractedExif.camera || 'לא זוהה' }}</p>
              <p><strong class="text-white">עדשה:</strong> {{ extractedExif.lens || 'לא צוין' }}</p>
              <p><strong class="text-white">חשיפה:</strong> {{ extractedExif.aperture }} • {{ extractedExif.shutterSpeed }} • ISO {{ extractedExif.iso }}</p>
            </div>
          </div>

          <!-- Bilingual Titles -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">כותרת (עברית):</label>
              <input v-model="titleHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">Title (English):</label>
              <input v-model="titleEn" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
          </div>

          <!-- Species Names -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">שם המין (עברית):</label>
              <input v-model="speciesHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">שם לטיני מדעי:</label>
              <input v-model="speciesLa" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white italic" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">English Species Name:</label>
              <input v-model="speciesEn" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
            </div>
          </div>

          <!-- Category -->
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">קטגוריה:</label>
            <select v-model="category" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white">
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
              <textarea v-model="descHe" rows="2" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white"></textarea>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">Description (English):</label>
              <textarea v-model="descEn" rows="2" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white"></textarea>
            </div>
          </div>

          <!-- Humorous Descriptions -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-amber-950/20 p-3 rounded-xl border border-amber-500/20">
            <div>
              <label class="block text-xs font-semibold text-amber-300 mb-1">🎭 משפט הומוריסטי (עברית):</label>
              <input v-model="humorHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-amber-100" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-amber-300 mb-1">🎭 Witty Caption (English):</label>
              <input v-model="humorEn" type="text" dir="ltr" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-amber-100" />
            </div>
          </div>

          <!-- Tags -->
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">תגיות (מופרדות בפסיקים):</label>
            <input v-model="tagsHe" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white" />
          </div>

          <!-- Checkboxes -->
          <div class="flex items-center gap-6 pt-1 text-xs">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="isFeatured" class="rounded text-amber-500" />
              <span>⭐ סמן כתמונה נבחרת (Featured)</span>
            </label>

            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="addToCurationExhibition" class="rounded text-indigo-500" />
              <span>🎨 הוסף מיד למאגר התערוכה</span>
            </label>
          </div>
        </div>

      </div>

      <!-- Modal Footer -->
      <footer class="p-4 border-t border-slate-800 flex items-center justify-between bg-slate-950/40">
        <button @click="emit('close')" class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer">ביטול</button>
        <button
          v-if="selectedFile && !isProcessing"
          @click="handlePublish"
          class="px-6 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition cursor-pointer shadow-lg flex items-center gap-2"
        >
          <span>🚀</span>
          <span>פרסם תמונה לאתר</span>
        </button>
      </footer>

    </div>
  </div>
</template>
