<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import {
  X,
  ChevronRight,
  ChevronLeft,
  Info,
  Camera,
  Aperture,
  Clock,
  Gauge,
  Calendar,
  MapPin,
  Tag,
  Maximize2,
  Share2,
  Check,
  ZoomIn,
  ZoomOut
} from 'lucide-vue-next';

const props = defineProps({
  photo: {
    type: Object,
    default: null
  },
  photosList: {
    type: Array,
    required: true
  }
});

const emit = defineEmits(['close', 'select-tag', 'navigate']);

// Drawer toggle state (always open by default so details are immediately visible)
const showDrawer = ref(true);
const isHighResLoaded = ref(false);
const isSlowLoading = ref(false);
let slowTimer = null;
const shareCopied = ref(false);

const handleShare = async () => {
  if (!props.photo || typeof window === 'undefined') return;

  const url = new URL(window.location.href);
  url.searchParams.set('photo', props.photo.id);
  const shareUrl = url.toString();

  const shareData = {
    title: props.photo.title || 'צילום מאת רועי גרינברג',
    text: `${props.photo.title || 'תמונת טבע'} | גלריית הצילום של רועי גרינברג`,
    url: shareUrl
  };

  // 1. Try native Web Share API (mobile devices)
  if (navigator.share && navigator.canShare && navigator.canShare(shareData)) {
    try {
      await navigator.share(shareData);
      return;
    } catch (err) {
      if (err.name === 'AbortError') return; // Cancelled by user
    }
  }

  // 2. Fallback: Copy direct URL to clipboard
  try {
    await navigator.clipboard.writeText(shareUrl);
    shareCopied.value = true;
    setTimeout(() => {
      shareCopied.value = false;
    }, 2500);
  } catch (err) {
    const ta = document.createElement('textarea');
    ta.value = shareUrl;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    shareCopied.value = true;
    setTimeout(() => {
      shareCopied.value = false;
    }, 2500);
  }
};

// Browser cache & preloader tracker
const preloadedUrls = new Set();

const preloadSingleImage = (url) => {
  if (!url || preloadedUrls.has(url)) return;
  preloadedUrls.add(url);
  const img = new Image();
  img.src = url;
};

// Current photo index
const currentIndex = computed(() => {
  if (!props.photo) return -1;
  return props.photosList.findIndex(p => p.id === props.photo.id);
});

const hasNext = computed(() => currentIndex.value < props.photosList.length - 1);
const hasPrev = computed(() => currentIndex.value > 0);

// Preload 2 next and 2 previous photos into browser cache
const preloadAdjacentPhotos = (index) => {
  if (index < 0 || !props.photosList || props.photosList.length === 0) return;

  // Priority order: next 1, previous 1, next 2, previous 2
  const steps = [1, -1, 2, -2];
  for (const step of steps) {
    const targetIdx = index + step;
    if (targetIdx >= 0 && targetIdx < props.photosList.length) {
      const p = props.photosList[targetIdx];
      if (p) {
        if (p.display) preloadSingleImage(p.display);
        if (p.thumbnail) preloadSingleImage(p.thumbnail);
      }
    }
  }
};

const handleHighResLoad = () => {
  isHighResLoaded.value = true;
  isSlowLoading.value = false;
  if (slowTimer) {
    clearTimeout(slowTimer);
    slowTimer = null;
  }
};

const checkAndPreloadCurrent = () => {
  if (!props.photo) return;

  if (slowTimer) {
    clearTimeout(slowTimer);
    slowTimer = null;
  }
  isSlowLoading.value = false;

  // Check if high-res image is already cached in browser
  const displayUrl = props.photo.display;
  if (displayUrl) {
    const testImg = new Image();
    testImg.src = displayUrl;
    if (testImg.complete) {
      isHighResLoaded.value = true;
    } else {
      isHighResLoaded.value = false;
      // If image takes more than 200ms to load, show gentle loading status
      slowTimer = setTimeout(() => {
        if (!isHighResLoaded.value) {
          isSlowLoading.value = true;
        }
      }, 200);
    }
  } else {
    isHighResLoaded.value = false;
  }

  // Preload next and previous photos in the background (microtask delay so current image takes network priority)
  setTimeout(() => {
    preloadAdjacentPhotos(currentIndex.value);
  }, 40);
};

// In RTL layout:
// "Next" image logically moves forward in the sequence
const goNext = () => {
  if (hasNext.value) {
    emit('navigate', props.photosList[currentIndex.value + 1]);
  }
};

const goPrev = () => {
  if (hasPrev.value) {
    emit('navigate', props.photosList[currentIndex.value - 1]);
  }
};

const handleClose = () => {
  emit('close');
};

const handleTagClick = (tag) => {
  emit('select-tag', tag);
};

// Format date strictly to DD/MM/YYYY
const formatDate = (dateStr) => {
  if (!dateStr || typeof dateStr !== 'string') return '';
  const match = dateStr.trim().match(/^(\d{4})[:\-](\d{2})[:\-](\d{2})/);
  if (match) {
    const [, year, month, day] = match;
    return `${day}/${month}/${year}`;
  }
  return dateStr;
};

// ==========================================
// Zoom & Pan Management (Prevents Swipe Conflict)
// ==========================================
const zoomScale = ref(1);
const panX = ref(0);
const panY = ref(0);
const isDragging = ref(false);
const dragStartX = ref(0);
const dragStartY = ref(0);
const initialPanX = ref(0);
const initialPanY = ref(0);
const lastTapTime = ref(0);
const isMultiTouch = ref(false);

const resetZoom = () => {
  zoomScale.value = 1;
  panX.value = 0;
  panY.value = 0;
  isDragging.value = false;
};

const toggleZoom = () => {
  if (zoomScale.value > 1) {
    resetZoom();
  } else {
    zoomScale.value = 2.4;
    panX.value = 0;
    panY.value = 0;
  }
};

// Double-tap and pan handling on image
const handleImageTouchStart = (e) => {
  if (e.touches && e.touches.length > 1) {
    isMultiTouch.value = true;
    return;
  }

  const now = Date.now();
  if (now - lastTapTime.value < 300) {
    toggleZoom();
    lastTapTime.value = 0;
    if (e.cancelable) e.preventDefault();
    return;
  }
  lastTapTime.value = now;

  if (zoomScale.value > 1 && e.touches) {
    isDragging.value = true;
    dragStartX.value = e.touches[0].clientX;
    dragStartY.value = e.touches[0].clientY;
    initialPanX.value = panX.value;
    initialPanY.value = panY.value;
  }
};

const handleImageTouchMove = (e) => {
  if (e.touches && e.touches.length > 1) {
    isMultiTouch.value = true;
    return;
  }

  if (zoomScale.value > 1 && isDragging.value && e.touches) {
    if (e.cancelable) e.preventDefault();
    const dx = e.touches[0].clientX - dragStartX.value;
    const dy = e.touches[0].clientY - dragStartY.value;
    panX.value = initialPanX.value + dx;
    panY.value = initialPanY.value + dy;
  }
};

const handleImageTouchEnd = () => {
  isDragging.value = false;
};

// Mouse pan for desktop
const handleMouseDown = (e) => {
  if (zoomScale.value > 1) {
    isDragging.value = true;
    dragStartX.value = e.clientX;
    dragStartY.value = e.clientY;
    initialPanX.value = panX.value;
    initialPanY.value = panY.value;
    e.preventDefault();
  }
};

const handleMouseMove = (e) => {
  if (zoomScale.value > 1 && isDragging.value) {
    const dx = e.clientX - dragStartX.value;
    const dy = e.clientY - dragStartY.value;
    panX.value = initialPanX.value + dx;
    panY.value = initialPanY.value + dy;
  }
};

const handleMouseUp = () => {
  isDragging.value = false;
};

// Outer Container Touch gestures / Swipe navigation
const touchStartX = ref(0);
const touchStartY = ref(0);

const handleTouchStart = (e) => {
  if (e.touches && e.touches.length > 1) {
    isMultiTouch.value = true;
    return;
  }
  isMultiTouch.value = false;
  touchStartX.value = e.changedTouches[0].screenX;
  touchStartY.value = e.changedTouches[0].screenY;
};

const handleTouchEnd = (e) => {
  // 1. If multi-touch (pinch) was used, NEVER swipe!
  if (isMultiTouch.value || (e.touches && e.touches.length > 0)) {
    isMultiTouch.value = false;
    return;
  }

  // 2. If browser viewport is zoomed (native mobile pinch zoom), NEVER swipe!
  if (typeof window !== 'undefined' && window.visualViewport && window.visualViewport.scale > 1.05) {
    return;
  }

  // 3. If image zoom is active (scale > 1), NEVER swipe!
  if (zoomScale.value > 1.05) {
    return;
  }

  const diffX = e.changedTouches[0].screenX - touchStartX.value;
  const diffY = e.changedTouches[0].screenY - touchStartY.value;

  // Ensure horizontal swipe is dominant and above threshold (40px)
  if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 40) {
    if (diffX > 0) {
      // Swiped right -> In RTL or standard swipe, go previous
      goPrev();
    } else {
      // Swiped left -> Go next
      goNext();
    }
  }
};

// Keyboard navigation
const handleKeyDown = (e) => {
  if (!props.photo) return;
  if (e.key === 'Escape') {
    if (zoomScale.value > 1) {
      resetZoom();
    } else {
      handleClose();
    }
  } else if (e.key === 'ArrowRight') {
    if (zoomScale.value <= 1.05) goPrev();
  } else if (e.key === 'ArrowLeft') {
    if (zoomScale.value <= 1.05) goNext();
  }
};

watch(() => props.photo, () => {
  resetZoom();
  checkAndPreloadCurrent();
}, { immediate: true });

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', handleKeyDown);
  }
  checkAndPreloadCurrent();
});

onUnmounted(() => {
  if (slowTimer) clearTimeout(slowTimer);
  window.removeEventListener('keydown', handleKeyDown);
});
</script>

<template>
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition duration-200 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="photo"
      class="fixed inset-0 z-50 flex flex-col bg-slate-950/95 backdrop-blur-xl select-none"
      @touchstart="handleTouchStart"
      @touchend="handleTouchEnd"
    >
      <!-- Top Action Bar -->
      <header class="shrink-0 flex items-center justify-between px-4 sm:px-6 py-3.5 z-20 border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
        <!-- Title & Counter -->
        <div class="flex items-center gap-3">
          <span class="text-xs px-2.5 py-1 rounded-full bg-slate-800/80 text-sky-400 font-mono">
            {{ currentIndex + 1 }} / {{ photosList.length }}
          </span>
          <h2 class="text-sm sm:text-base font-semibold text-slate-100 truncate max-w-[200px] sm:max-w-md">
            {{ photo.title }}
          </h2>
        </div>

        <!-- Controls -->
        <div class="flex items-center gap-2">
          <!-- Toggle Zoom Button -->
          <button
            @click="toggleZoom"
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition cursor-pointer',
              zoomScale > 1
                ? 'bg-sky-500/20 text-sky-300 border-sky-500/50 ring-1 ring-sky-500/30'
                : 'border-slate-800 bg-slate-900/90 text-slate-300 hover:text-white hover:border-slate-700'
            ]"
            :title="zoomScale > 1 ? 'אפס זום' : 'הגדל תמונה (זום)'"
          >
            <ZoomOut v-if="zoomScale > 1" class="w-3.5 h-3.5 text-sky-400" />
            <ZoomIn v-else class="w-3.5 h-3.5" />
            <span class="hidden sm:inline">{{ zoomScale > 1 ? 'אפס זום' : 'זום' }}</span>
          </button>

          <!-- Share Direct Link Button -->
          <button
            @click="handleShare"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-slate-800 bg-slate-900/90 text-slate-300 hover:text-white hover:border-slate-700 transition cursor-pointer"
            title="שתף קישור ישיר לתמונה"
          >
            <Check v-if="shareCopied" class="w-3.5 h-3.5 text-emerald-400" />
            <Share2 v-else class="w-3.5 h-3.5" />
            <span class="text-xs">{{ shareCopied ? 'הועתק!' : 'שתף' }}</span>
          </button>

          <!-- Toggle Metadata Drawer Button -->
          <button
            @click="showDrawer = !showDrawer"
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition cursor-pointer',
              showDrawer
                ? 'bg-sky-500/10 text-sky-400 border-sky-500/40'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
            ]"
            title="הצג / הסתר פרטי EXIF ומידע"
          >
            <Info class="w-3.5 h-3.5" />
            <span class="hidden sm:inline">{{ showDrawer ? 'הסתר מידע' : 'פרטי תמונה' }}</span>
          </button>

          <!-- Close Lightbox -->
          <button
            @click="handleClose"
            class="p-2 rounded-full text-slate-400 hover:text-white hover:bg-slate-800/80 transition cursor-pointer"
            aria-label="סגור תצוגה מוגדלת"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      </header>

      <!-- Main Content Area: Image + Floating Navigation + Metadata Drawer -->
      <div class="relative flex-1 min-h-0 min-w-0 flex flex-col lg:flex-row overflow-hidden">
        
        <!-- Large Image Stage -->
        <div class="relative flex-1 min-h-0 min-w-0 w-full h-full flex items-center justify-center p-2 sm:p-4 lg:p-6 overflow-hidden">
          
          <!-- Floating Zoom Reset Bar when zoomed in -->
          <div
            v-if="zoomScale > 1"
            class="absolute top-4 left-1/2 -translate-x-1/2 z-30 px-4 py-1.5 rounded-full bg-slate-950/85 text-white border border-white/20 shadow-2xl backdrop-blur-md flex items-center gap-3 text-xs pointer-events-auto"
          >
            <span class="text-sky-400 font-bold font-mono">{{ zoomScale.toFixed(1) }}x</span>
            <span class="text-slate-300 text-[11px] hidden sm:inline">גרור להזזה • הקש פעמיים לאיפוס</span>
            <button
              type="button"
              @click.stop="resetZoom"
              class="px-2.5 py-0.5 rounded-full bg-sky-500 hover:bg-sky-400 text-slate-950 text-xs font-bold transition cursor-pointer"
            >
              אפס גודל
            </button>
          </div>

          <!-- Navigation Arrow Right (Previous in RTL) - Hidden on mobile or when zoomed -->
          <button
            v-if="hasPrev && zoomScale <= 1.05"
            @click.stop="goPrev"
            class="hidden md:flex absolute right-3 sm:right-6 top-1/2 -translate-y-1/2 z-20 p-3 rounded-full bg-slate-900/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-white/10 shadow-xl backdrop-blur-md transition-transform hover:scale-110 active:scale-95 cursor-pointer items-center justify-center"
            aria-label="התמונה הקודמת"
          >
            <ChevronRight class="w-6 h-6" />
          </button>

          <!-- Navigation Arrow Left (Next in RTL) - Hidden on mobile or when zoomed -->
          <button
            v-if="hasNext && zoomScale <= 1.05"
            @click.stop="goNext"
            class="hidden md:flex absolute left-3 sm:left-6 top-1/2 -translate-y-1/2 z-20 p-3 rounded-full bg-slate-900/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-white/10 shadow-xl backdrop-blur-md transition-transform hover:scale-110 active:scale-95 cursor-pointer items-center justify-center"
            aria-label="התמונה הבאה"
          >
            <ChevronLeft class="w-6 h-6" />
          </button>

          <!-- Image Container with Progressive Fade-in & Full Vertical/Horizontal Fit -->
          <div
            class="relative flex items-center justify-center w-full h-full max-w-full max-h-full overflow-hidden select-none"
            @mousedown="handleMouseDown"
            @mousemove="handleMouseMove"
            @mouseup="handleMouseUp"
            @touchstart="handleImageTouchStart"
            @touchmove="handleImageTouchMove"
            @touchend="handleImageTouchEnd"
            @dblclick="toggleZoom"
          >
            <!-- Zoom transform wrapper -->
            <div
              class="relative flex items-center justify-center max-w-full max-h-full"
              :style="{
                transform: `scale(${zoomScale}) translate(${panX / zoomScale}px, ${panY / zoomScale}px)`,
                transition: isDragging ? 'none' : 'transform 200ms cubic-bezier(0.2, 0, 0, 1)',
                cursor: zoomScale > 1 ? (isDragging ? 'grabbing' : 'grab') : 'zoom-in'
              }"
            >
              <!-- Low-res thumbnail placeholder while display image loads (instant LQIP) -->
              <img
                :src="photo.thumbnail"
                :alt="photo.title"
                class="max-w-full max-h-full w-auto h-auto object-contain rounded-lg sm:rounded-xl shadow-2xl transition-all duration-300 filter select-none pointer-events-none"
                :class="isHighResLoaded ? 'opacity-0 blur-0 scale-100 absolute inset-0 m-auto' : 'opacity-100 blur-sm scale-100'"
                loading="eager"
                decoding="sync"
                draggable="false"
              />

              <!-- High-Res Display Image -->
              <img
                :src="photo.display"
                :alt="photo.title"
                @load="handleHighResLoad"
                class="max-w-full max-h-full w-auto h-auto object-contain rounded-lg sm:rounded-xl shadow-2xl transition-opacity duration-300 select-none pointer-events-none"
                :class="isHighResLoaded ? 'opacity-100 relative' : 'opacity-0 absolute inset-0 m-auto'"
                loading="eager"
                decoding="async"
                draggable="false"
              />
            </div>

            <!-- Subtle loading badge if high-res takes more than 200ms -->
            <Transition
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="opacity-0 translate-y-2"
              enter-to-class="opacity-100 translate-y-0"
              leave-active-class="transition duration-150 ease-in"
              leave-from-class="opacity-100 translate-y-0"
              leave-to-class="opacity-0 translate-y-2"
            >
              <div
                v-if="!isHighResLoaded && isSlowLoading"
                class="absolute bottom-4 z-20 px-4 py-1.5 rounded-full bg-slate-950/80 backdrop-blur-md border border-white/10 shadow-xl flex items-center gap-2 pointer-events-none"
              >
                <span class="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
                <span class="text-xs text-slate-300 font-medium">טוען באיכות מלאה...</span>
              </div>
            </Transition>
          </div>
        </div>

        <!-- Metadata Drawer (Side on Desktop, Bottom sheet on Mobile) -->
        <Transition
          enter-active-class="transition duration-300 ease-out"
          enter-from-class="translate-x-full lg:translate-x-full lg:translate-y-0 translate-y-full"
          enter-to-class="translate-x-0 translate-y-0"
          leave-active-class="transition duration-200 ease-in"
          leave-from-class="translate-x-0 translate-y-0"
          leave-to-class="translate-x-full lg:translate-x-full lg:translate-y-0 translate-y-full"
        >
          <aside
            v-if="showDrawer"
            class="w-full lg:w-96 shrink-0 max-h-[40vh] lg:max-h-full overflow-y-auto bg-slate-900/90 border-t lg:border-t-0 lg:border-r border-slate-800/90 backdrop-blur-2xl p-5 sm:p-6 space-y-6 text-right z-30 shadow-2xl"
          >
            <!-- Title and taxonomy -->
            <div>
              <span class="inline-block px-2.5 py-1 text-xs font-medium text-sky-400 bg-sky-950/60 border border-sky-800/50 rounded-full mb-2">
                {{ photo.category }}
              </span>
              <h3 class="text-xl font-bold text-white tracking-tight leading-snug">
                {{ photo.title }}
              </h3>
              <p class="text-sm text-sky-300 font-medium mt-1">
                {{ photo.species_he }}
                <span v-if="photo.species_la" class="text-slate-400 font-normal italic block text-xs">
                  ({{ photo.species_la }})
                </span>
              </p>
            </div>

            <!-- Description -->
            <p class="text-xs sm:text-sm text-slate-300 leading-relaxed bg-slate-950/40 p-3.5 rounded-xl border border-white/5">
              {{ photo.description }}
            </p>

            <!-- EXIF & Gear Specs Grid -->
            <div class="space-y-3">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Camera class="w-3.5 h-3.5 text-sky-400" />
                <span>נתוני חשיפה וציוד (EXIF)</span>
              </h4>

              <div class="grid grid-cols-2 gap-2 text-xs">
                <!-- Camera Model -->
                <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80 col-span-2">
                  <span class="text-slate-500 block text-[10px]">גוף מצלמה</span>
                  <span class="text-slate-200 font-medium truncate block">{{ photo.exif.camera }}</span>
                </div>

                <!-- Lens -->
                <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80 col-span-2">
                  <span class="text-slate-500 block text-[10px]">עדשה</span>
                  <span class="text-slate-200 font-medium truncate block">{{ photo.exif.lens }}</span>
                </div>

                <!-- Focal Length -->
                <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80">
                  <span class="text-slate-500 block text-[10px]">אורך מוקד</span>
                  <span class="text-slate-200 font-mono">{{ photo.exif.focalLength }}</span>
                </div>

                <!-- Aperture -->
                <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80">
                  <span class="text-slate-500 block text-[10px]">צמצם</span>
                  <span class="text-slate-200 font-mono">{{ photo.exif.aperture }}</span>
                </div>

                <!-- Shutter Speed -->
                <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80">
                  <span class="text-slate-500 block text-[10px]">מהירות תריס</span>
                  <span class="text-slate-200 font-mono">{{ photo.exif.shutterSpeed }}</span>
                </div>

                <!-- ISO -->
                <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80">
                  <span class="text-slate-500 block text-[10px]">רגישות ISO</span>
                  <span class="text-slate-200 font-mono">{{ photo.exif.iso }}</span>
                </div>

                <!-- Location -->
                <div v-if="photo.exif.location" class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80 col-span-2 flex items-center gap-2">
                  <MapPin class="w-3.5 h-3.5 text-sky-400 shrink-0" />
                  <span class="text-slate-300 text-xs truncate">{{ photo.exif.location }}</span>
                </div>

                <!-- Date -->
                <div v-if="photo.exif.date" class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80 col-span-2 flex items-center gap-2">
                  <Calendar class="w-3.5 h-3.5 text-slate-500 shrink-0" />
                  <span class="text-slate-400 text-xs font-mono">{{ formatDate(photo.exif.date) }}</span>
                </div>
              </div>
            </div>

            <!-- Tags / Behaviors -->
            <div class="space-y-2">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Tag class="w-3.5 h-3.5 text-sky-400" />
                <span>תגיות והתנהגויות</span>
              </h4>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="t in photo.tags"
                  :key="t"
                  @click="handleTagClick(t)"
                  class="px-2.5 py-1 text-xs rounded-lg bg-slate-800/90 text-slate-300 hover:bg-sky-500 hover:text-white transition duration-150 border border-slate-700/60 cursor-pointer"
                  :title="'סנן גלריה לפי ' + t"
                >
                  #{{ t }}
                </button>
              </div>
            </div>
          </aside>
        </Transition>
      </div>
    </div>
  </Transition>
</template>
