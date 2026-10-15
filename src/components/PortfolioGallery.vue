<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import FilterBar from './FilterBar.vue';
import GalleryGrid from './GalleryGrid.vue';
import Lightbox from './Lightbox.vue';
import SelectionModal from './SelectionModal.vue';

const props = defineProps({
  initialPhotos: {
    type: Array,
    required: true
  }
});

// Category mapping: Normalize English categories to Hebrew UI labels
const categoryMap = {
  'wildlife': 'טבע וציפורים',
  'landscape': 'נוף',
  'astrophotography': 'אסטרופוטוגרפיה',
  'macro': 'מאקרו',
  'nature': 'טבע וציפורים',
  'portrait': 'טבע וציפורים',
  'other': 'נוף'
};

const getCategoryHebrew = (cat) => {
  return categoryMap[cat] || cat || 'טבע וציפורים';
};

// Format any date or EXIF timestamp to DD/MM/YYYY
const formatDateDDMMYYYY = (dateStr) => {
  if (!dateStr || typeof dateStr !== 'string') return '';
  const clean = dateStr.trim();
  if (!clean) return '';

  // Match EXIF "YYYY:MM:DD" or standard "YYYY-MM-DD"
  const match = clean.match(/^(\d{4})[:\-](\d{2})[:\-](\d{2})/);
  if (match) {
    const [, year, month, day] = match;
    return `${day}/${month}/${year}`;
  }

  try {
    const parsed = new Date(clean.replace(/:/g, '-'));
    if (!isNaN(parsed.getTime())) {
      const d = String(parsed.getDate()).padStart(2, '0');
      const m = String(parsed.getMonth() + 1).padStart(2, '0');
      const y = parsed.getFullYear();
      return `${d}/${m}/${y}`;
    }
  } catch (e) {}

  return clean;
};

// Normalize raw photo records to standard flat format used by components
const normalizedPhotos = computed(() => {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');

  return props.initialPhotos.map(p => {
    // Check if fields are nested under .ai (output of process_photos.py) or top-level
    const ai = p.ai || {};
    const exif = p.exif || {};
    const paths = p.paths || {};

    const rawThumb = p.thumb_url || paths.thumbnail || p.thumbnail || '';
    const rawDisplay = p.display_url || paths.display || p.display || '';

    // Build absolute URL taking Astro base path into account
    const fixUrl = (url) => {
      if (!url) return '';
      if (url.startsWith('http://') || url.startsWith('https://')) return url;
      const clean = url.startsWith('/') ? url : `/${url}`;
      return `${base}${clean}`;
    };

    const tags = Array.isArray(ai.tags) ? ai.tags : (Array.isArray(p.tags) ? p.tags : []);
    const behavior = Array.isArray(ai.behavior) ? ai.behavior : [];
    const allPhotoTags = Array.from(new Set([...tags, ...behavior])).filter(Boolean);

    const rawHumor = (
      ai.humorous_description ||
      p.humorous_description ||
      ai.humor ||
      p.humor ||
      ai.funny_caption ||
      p.funny_caption ||
      ''
    ).trim();

    return {
      id: p.id || p.filename || String(Math.random()),
      title: ai.title || p.title || p.filename || 'תמונת טבע',
      species_he: ai.species_hebrew || p.species_he || '',
      species_la: ai.species_latin || p.species_la || '',
      category: getCategoryHebrew(ai.category || p.category),
      is_featured: Boolean(p.is_featured),
      description: ai.description || p.description || '',
      humorous_description: rawHumor,
      has_humor: Boolean(rawHumor),
      thumbnail: fixUrl(rawThumb),
      display: fixUrl(rawDisplay),
      aspectRatio: p.dimensions?.aspect_ratio ? `${p.dimensions.aspect_ratio}` : (p.aspectRatio || '3/2'),
      width: p.dimensions?.width || p.width || 2048,
      height: p.dimensions?.height || p.height || 1366,
      tags: allPhotoTags,
      exif: {
        camera: exif.camera_model || exif.camera || 'Canon EOS',
        lens: exif.lens_model || exif.lens || '',
        focalLength: exif.focal_length || exif.focalLength || '',
        aperture: exif.aperture || '',
        shutterSpeed: exif.shutter_speed || exif.shutterSpeed || '',
        iso: exif.iso ? String(exif.iso) : '',
        date: formatDateDDMMYYYY(exif.date_time_original || exif.date || ''),
        location: exif.location || ''
      }
    };
  });
});

// Categories list in UI - Featured photos is the default first category
const categories = ['נבחרות ⭐', 'הכל', 'טבע וציפורים', 'נוף', 'אסטרופוטוגרפיה', 'מאקרו'];

// Active filter states - default to 'נבחרות ⭐'
const activeCategory = ref('נבחרות ⭐');
const searchQuery = ref('');
const activeTag = ref(null);
const activePhoto = ref(null);
const isHumorMode = ref(false);

const HUMOR_STORAGE_KEY = 'roigreenberg_humor_mode';

const toggleHumorMode = () => {
  isHumorMode.value = !isHumorMode.value;
  if (isHumorMode.value) {
    // If activating humor mode while on default 'נבחרות ⭐', switch to 'הכל'
    // so user immediately sees all 900+ humorous photos across the entire gallery!
    if (activeCategory.value === 'נבחרות ⭐') {
      activeCategory.value = 'הכל';
    }
  } else {
    // When exiting humor mode, restore the default featured landing view
    if (activeCategory.value === 'הכל') {
      activeCategory.value = 'נבחרות ⭐';
    }
  }
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(HUMOR_STORAGE_KEY, String(isHumorMode.value));
    } catch (e) {}
  }
};

// Count of photos with humorous descriptions
const humorCount = computed(() => {
  return normalizedPhotos.value.filter(p => p.has_humor).length;
});

// Extract top tags from normalized photos
const allTags = computed(() => {
  const counts = {};
  normalizedPhotos.value.forEach(p => {
    (p.tags || []).forEach(t => {
      if (t && t.length > 1 && !t.includes('אסטרונומ')) {
        counts[t] = (counts[t] || 0) + 1;
      }
    });
  });
  return Object.keys(counts)
    .sort((a, b) => counts[b] - counts[a])
    .slice(0, 12);
});

// Filtered photos computed property
const filteredPhotos = computed(() => {
  return normalizedPhotos.value.filter(photo => {
    // 0. Humor Mode check: in humor mode, strictly include only photos with humorous descriptions
    if (isHumorMode.value && !photo.has_humor) {
      return false;
    }

    // 1. Category check
    if (activeCategory.value === 'נבחרות ⭐') {
      if (!photo.is_featured) return false;
    } else if (activeCategory.value !== 'הכל' && photo.category !== activeCategory.value) {
      return false;
    }

    // 2. Tag check
    if (activeTag.value && !(photo.tags || []).includes(activeTag.value)) {
      return false;
    }

    // 3. Search query check (Hebrew species, Latin species, title, humorous description, camera, lens, tags)
    const q = searchQuery.value.trim().toLowerCase();
    if (q) {
      const matchTitle = photo.title?.toLowerCase().includes(q);
      const matchHumor = photo.humorous_description?.toLowerCase().includes(q);
      const matchSpeciesHe = photo.species_he?.toLowerCase().includes(q);
      const matchSpeciesLa = photo.species_la?.toLowerCase().includes(q);
      const matchCamera = photo.exif?.camera?.toLowerCase().includes(q);
      const matchLens = photo.exif?.lens?.toLowerCase().includes(q);
      const matchTags = (photo.tags || []).some(t => t.toLowerCase().includes(q));

      if (!matchTitle && !matchHumor && !matchSpeciesHe && !matchSpeciesLa && !matchCamera && !matchLens && !matchTags) {
        return false;
      }
    }

    return true;
  });
});

// ==========================================
// Virtual Pagination & Infinite Scroll (Batch of 30)
// ==========================================
const PAGE_SIZE = 30;
const visibleCount = ref(PAGE_SIZE);
const sentinelRef = ref(null);
let observer = null;

// Reset pagination whenever filters or humor mode change
watch([activeCategory, searchQuery, activeTag, isHumorMode], () => {
  visibleCount.value = PAGE_SIZE;
});

// Sliced list of photos currently rendered in the DOM
const visiblePhotos = computed(() => {
  return filteredPhotos.value.slice(0, visibleCount.value);
});

const hasMore = computed(() => {
  return visibleCount.value < filteredPhotos.value.length;
});

const loadMore = () => {
  if (hasMore.value) {
    visibleCount.value = Math.min(visibleCount.value + PAGE_SIZE, filteredPhotos.value.length);
  }
};

const setupObserver = () => {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) return;
  if (!sentinelRef.value) return;

  observer = new IntersectionObserver((entries) => {
    const entry = entries[0];
    if (entry && entry.isIntersecting && hasMore.value) {
      loadMore();
    }
  }, {
    root: null,
    rootMargin: '600px 0px', // Pre-load 600px before user reaches the bottom
    threshold: 0
  });

  observer.observe(sentinelRef.value);
};

// ==========================================
// Client Selection & LocalStorage Sync
// ==========================================
const STORAGE_KEY = 'roigreenberg_selected_photos';
const selectedPhotoIds = ref([]);
const isSelectionModalOpen = ref(false);

const loadSavedSelections = () => {
  if (typeof window === 'undefined') return;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed)) {
        selectedPhotoIds.value = parsed;
      }
    }
  } catch (e) {
    console.error('Failed to load selected photos from localStorage', e);
  }
};

watch(selectedPhotoIds, (newIds) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newIds));
  } catch (e) {
    console.error('Failed to save selected photos to localStorage', e);
  }
}, { deep: true });

const selectedPhotos = computed(() => {
  const set = new Set(selectedPhotoIds.value);
  return normalizedPhotos.value.filter(p => set.has(p.id));
});

const togglePhotoSelection = (photo) => {
  const idx = selectedPhotoIds.value.indexOf(photo.id);
  if (idx >= 0) {
    selectedPhotoIds.value.splice(idx, 1);
  } else {
    selectedPhotoIds.value.push(photo.id);
  }
};

const removePhotoSelection = (photoId) => {
  selectedPhotoIds.value = selectedPhotoIds.value.filter(id => id !== photoId);
};

const clearPhotoSelection = () => {
  selectedPhotoIds.value = [];
};

const openSelectionModal = () => {
  isSelectionModalOpen.value = true;
};

const closeSelectionModal = () => {
  isSelectionModalOpen.value = false;
};

// ==========================================
// URL Deep Linking & Shareable State Sync
// ==========================================
let isSyncingFromUrl = false;

const syncStateFromUrl = () => {
  if (typeof window === 'undefined') return;
  isSyncingFromUrl = true;

  try {
    const params = new URLSearchParams(window.location.search);

    // 1. Humor Mode
    const humorParam = params.get('humor') || params.get('mode');
    if (humorParam === '1' || humorParam === 'true' || humorParam === 'humor') {
      isHumorMode.value = true;
    } else if (humorParam === '0' || humorParam === 'false') {
      isHumorMode.value = false;
    } else if (typeof window !== 'undefined') {
      try {
        const savedHumor = localStorage.getItem(HUMOR_STORAGE_KEY);
        if (savedHumor === 'true') {
          isHumorMode.value = true;
        }
      } catch (e) {}
    }

    // 2. Category
    const cat = params.get('category');
    if (cat) {
      if (cat === 'all' || cat === 'הכל') {
        activeCategory.value = 'הכל';
      } else if (cat === 'featured' || cat === 'נבחרות' || cat === 'נבחרות ⭐') {
        activeCategory.value = 'נבחרות ⭐';
      } else {
        const found = categories.find(c => c === cat || c.includes(cat));
        if (found) {
          activeCategory.value = found;
        } else if (categoryMap[cat]) {
          activeCategory.value = categoryMap[cat];
        }
      }
    } else {
      // In humor mode default to 'הכל' to reveal all 934 funny photos, else default to 'נבחרות ⭐'
      activeCategory.value = isHumorMode.value ? 'הכל' : 'נבחרות ⭐';
    }

    // 3. Tag
    const tag = params.get('tag');
    if (tag) {
      activeTag.value = tag;
    }

    // 4. Search query
    const q = params.get('q');
    if (q) {
      searchQuery.value = q;
    }

    // 5. Photo in lightbox
    const photoId = params.get('photo');
    if (photoId) {
      const match = normalizedPhotos.value.find(p => p.id === photoId);
      if (match) {
        activePhoto.value = match;
        const idx = filteredPhotos.value.findIndex(p => p.id === match.id);
        if (idx >= visibleCount.value) {
          visibleCount.value = Math.min(idx + PAGE_SIZE, filteredPhotos.value.length);
        }
      } else {
        activePhoto.value = null;
      }
    } else {
      activePhoto.value = null;
    }
  } finally {
    setTimeout(() => {
      isSyncingFromUrl = false;
    }, 0);
  }
};

const updateUrl = (pushToHistory = false) => {
  if (typeof window === 'undefined' || isSyncingFromUrl) return;

  const url = new URL(window.location.href);
  const params = url.searchParams;

  // Category (omitted when default for current mode: 'הכל' in humor mode, 'נבחרות ⭐' in normal mode)
  const defaultCategory = isHumorMode.value ? 'הכל' : 'נבחרות ⭐';
  if (activeCategory.value && activeCategory.value !== defaultCategory) {
    params.set('category', activeCategory.value);
  } else {
    params.delete('category');
  }

  // Humor Mode
  if (isHumorMode.value) {
    params.set('humor', '1');
  } else {
    params.delete('humor');
  }

  // Tag
  if (activeTag.value) {
    params.set('tag', activeTag.value);
  } else {
    params.delete('tag');
  }

  // Search query
  if (searchQuery.value && searchQuery.value.trim()) {
    params.set('q', searchQuery.value.trim());
  } else {
    params.delete('q');
  }

  // Photo
  if (activePhoto.value?.id) {
    params.set('photo', activePhoto.value.id);
  } else {
    params.delete('photo');
  }

  const queryString = params.toString() ? `?${params.toString()}` : '';
  const newUrl = `${url.pathname}${queryString}${url.hash}`;

  if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== newUrl) {
    if (pushToHistory) {
      window.history.pushState(null, '', newUrl);
    } else {
      window.history.replaceState(null, '', newUrl);
    }
  }
};

onMounted(() => {
  setupObserver();
  loadSavedSelections();
  syncStateFromUrl();
  window.addEventListener('popstate', syncStateFromUrl);
});

watch([activeCategory, searchQuery, activeTag, isHumorMode], () => {
  updateUrl(false);
});

watch(activePhoto, (newVal, oldVal) => {
  // If opening photo from closed state, push history so browser back button closes it
  const shouldPush = !oldVal && newVal;
  updateUrl(shouldPush);
});

onUnmounted(() => {
  if (observer) {
    observer.disconnect();
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('popstate', syncStateFromUrl);
  }
});

const handleCategoryChange = (cat) => {
  activeCategory.value = cat;
};

const handleSearchChange = (query) => {
  searchQuery.value = query;
};

const handleTagChange = (tag) => {
  activeTag.value = tag;
};

const resetFilters = () => {
  activeCategory.value = 'נבחרות ⭐';
  searchQuery.value = '';
  activeTag.value = null;
  isHumorMode.value = false;
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem(HUMOR_STORAGE_KEY);
    } catch (e) {}
  }
};

const openPhoto = (photo) => {
  activePhoto.value = photo;
};

const closePhoto = () => {
  activePhoto.value = null;
};

const selectTagFromLightbox = (tag) => {
  activePhoto.value = null;
  activeTag.value = tag;
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

const navigateToPhoto = (photo) => {
  activePhoto.value = photo;
  // Ensure the photo navigated to in lightbox is included in visible photos
  const idx = filteredPhotos.value.findIndex(p => p.id === photo.id);
  if (idx >= visibleCount.value) {
    visibleCount.value = Math.min(idx + PAGE_SIZE, filteredPhotos.value.length);
  }
};
</script>

<template>
  <div class="space-y-4">
    <!-- Filter and Search Bar -->
    <FilterBar
      :categories="categories"
      :activeCategory="activeCategory"
      :searchQuery="searchQuery"
      :allTags="allTags"
      :activeTag="activeTag"
      :filteredCount="filteredPhotos.length"
      :totalCount="normalizedPhotos.length"
      :selectedCount="selectedPhotoIds.length"
      :isHumorMode="isHumorMode"
      :humorCount="humorCount"
      @update:category="handleCategoryChange"
      @update:search="handleSearchChange"
      @update:tag="handleTagChange"
      @toggle-humor="toggleHumorMode"
      @reset-filters="resetFilters"
      @open-selection="openSelectionModal"
    />

    <!-- Humor Mode Banner (when active) -->
    <div
      v-if="isHumorMode"
      class="rounded-2xl border border-amber-500/30 bg-gradient-to-r from-amber-500/15 via-purple-950/30 to-slate-900/40 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 backdrop-blur-md shadow-lg"
    >
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-amber-500/20 text-amber-300 flex items-center justify-center text-xl shrink-0 border border-amber-500/40 shadow-inner">
          🎭
        </div>
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <h2 class="text-white font-bold text-base sm:text-lg">מצב הומוריסטי פעיל</h2>
            <span class="px-2.5 py-0.5 rounded-full bg-amber-400/20 text-amber-300 text-xs font-bold border border-amber-400/30">
              {{ filteredPhotos.length }} תמונות
            </span>
            <span v-if="activeCategory !== 'הכל'" class="text-xs text-amber-300/80">
              (מסונן לפי: {{ activeCategory }} מתוך {{ humorCount }} סה״כ)
            </span>
          </div>
          <p class="text-xs sm:text-sm text-slate-300 mt-0.5">
            מוצגות רק תמונות שזוהו כבעלות זווית משעשעת או הבעה מצחיקה, והתיאורים מוחלפים בכיתובים שנונים.
            <span v-if="activeCategory !== 'הכל'">
              <button
                type="button"
                @click="activeCategory = 'הכל'"
                class="underline hover:text-white mr-1.5 cursor-pointer font-bold text-amber-300 transition-colors"
              >
                לחץ כאן לצפייה בכל {{ humorCount }} התמונות ההומוריסטיות בגלריה
              </button>
            </span>
          </p>
        </div>
      </div>
      <button
        type="button"
        @click="toggleHumorMode"
        class="self-start sm:self-auto px-4 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-700 text-slate-200 hover:text-white text-xs font-semibold border border-slate-700 shrink-0 transition-colors cursor-pointer"
      >
        חזור למצב רגיל
      </button>
    </div>

    <!-- Featured Category Banner -->
    <div
      v-else-if="activeCategory === 'נבחרות ⭐'"
      class="rounded-2xl border border-amber-500/20 bg-gradient-to-r from-amber-500/10 via-amber-950/20 to-transparent p-4 sm:p-5 flex items-center justify-between gap-4 backdrop-blur-sm"
    >
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center text-xl shrink-0 border border-amber-500/30">
          ⭐
        </div>
        <div>
          <h2 class="text-white font-bold text-base sm:text-lg">תמונות נבחרות מהפורטפוליו</h2>
          <p class="text-xs sm:text-sm text-slate-400">
            אוסף הצילומים המובחרים. ניתן לסמן תמונות ב-➕ וללחוץ על ״תמונות שבחרתי״ לשליחת הרשימה בוואטסאפ.
          </p>
        </div>
      </div>
      <button
        v-if="selectedPhotoIds.length > 0"
        type="button"
        @click="openSelectionModal"
        class="hidden sm:flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shrink-0 transition-colors cursor-pointer"
      >
        <span>צפה בבחירה</span>
        <span class="bg-black/20 px-2 py-0.5 rounded-full text-[11px]">{{ selectedPhotoIds.length }}</span>
      </button>
    </div>

    <!-- Masonry Grid with paged visible items -->
    <GalleryGrid
      :photos="visiblePhotos"
      :selectedIds="selectedPhotoIds"
      :isHumorMode="isHumorMode"
      @select-photo="openPhoto"
      @toggle-select="togglePhotoSelection"
    />

    <!-- Invisible Sentinel for smooth automatic infinite scroll -->
    <div ref="sentinelRef" class="w-full h-8 pointer-events-none opacity-0"></div>

    <!-- Fallback Load More button (seen only if user scrolls faster than network or observer) -->
    <div v-if="hasMore" class="flex flex-col items-center justify-center pt-2 pb-12">
      <button
        type="button"
        @click="loadMore"
        class="px-8 py-3 rounded-full bg-slate-900/90 hover:bg-slate-800 text-sky-400 hover:text-white border border-slate-700/80 hover:border-sky-500/60 font-semibold text-sm transition-all duration-200 shadow-lg hover:shadow-sky-500/10 flex items-center gap-2.5 cursor-pointer active:scale-95"
      >
        <span class="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
        <span>טען עוד 30 תמונות</span>
        <span class="text-xs font-normal text-slate-400">({{ visiblePhotos.length }} מתוך {{ filteredPhotos.length }})</span>
      </button>
    </div>
    <div v-else-if="filteredPhotos.length > PAGE_SIZE" class="text-center py-8 text-xs text-slate-500">
      ✓ הוצגו כל {{ filteredPhotos.length }} התמונות
    </div>

    <!-- Floating Selection Pill when photos are selected -->
    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="transform translate-y-8 opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform translate-y-8 opacity-0"
    >
      <div
        v-if="selectedPhotoIds.length > 0"
        class="fixed bottom-6 right-6 z-40 flex items-center shadow-2xl"
      >
        <button
          type="button"
          @click="openSelectionModal"
          class="px-5 py-3 rounded-full bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-sm flex items-center gap-3 shadow-lg shadow-amber-500/30 hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer"
        >
          <span class="text-base">📋</span>
          <span>נבחרו {{ selectedPhotoIds.length }} תמונות</span>
          <span class="bg-black/20 text-xs px-2.5 py-0.5 rounded-full font-mono">פתח</span>
        </button>
      </div>
    </transition>

    <!-- Client Selection & WhatsApp Export Modal -->
    <SelectionModal
      :isOpen="isSelectionModalOpen"
      :selectedPhotos="selectedPhotos"
      @close="closeSelectionModal"
      @remove="removePhotoSelection"
      @clear="clearPhotoSelection"
    />

    <!-- Lightbox Modal -->
    <Lightbox
      :photo="activePhoto"
      :photosList="filteredPhotos"
      :isHumorMode="isHumorMode"
      @close="closePhoto"
      @navigate="navigateToPhoto"
      @select-tag="selectTagFromLightbox"
    />
  </div>
</template>
