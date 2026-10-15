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

// Format any date or EXIF timestamp to DD/MM/YYYY while preserving time (HH:MM:SS)
const formatDateDDMMYYYY = (dateStr) => {
  if (!dateStr || typeof dateStr !== 'string') return '';
  const clean = dateStr.trim();
  if (!clean) return '';

  // If already formatted as DD/MM/YYYY
  if (/^\d{2}\/\d{2}\/\d{4}/.test(clean)) return clean;

  // Match EXIF "YYYY:MM:DD HH:MM:SS" or standard "YYYY-MM-DD HH:MM:SS"
  const match = clean.match(/^(\d{4})[:\-](\d{2})[:\-](\d{2})(?:[T\s](\d{2}:\d{2}(?::\d{2})?))?/);
  if (match) {
    const [, year, month, day, time] = match;
    return time ? `${day}/${month}/${year} ${time}` : `${day}/${month}/${year}`;
  }

  try {
    const parsed = new Date(clean.replace(/:/g, '-'));
    if (!isNaN(parsed.getTime())) {
      const d = String(parsed.getDate()).padStart(2, '0');
      const m = String(parsed.getMonth() + 1).padStart(2, '0');
      const y = parsed.getFullYear();
      const hh = String(parsed.getHours()).padStart(2, '0');
      const mm = String(parsed.getMinutes()).padStart(2, '0');
      const ss = String(parsed.getSeconds()).padStart(2, '0');
      return `${d}/${m}/${y} ${hh}:${mm}:${ss}`;
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

    // Extract clean comparable capture timestamp (YYYYMMDDHHMMSS)
    const rawDate = exif.date_time_original || exif.date || '';
    let captureTs = '00000000000000';
    const matchExif = rawDate.match(/^(\d{4})[:\-](\d{2})[:\-](\d{2})\s*(\d{2})?[:\-]?(\d{2})?[:\-]?(\d{2})?/);
    if (matchExif) {
      const [, y, m, d, hh = '00', mm = '00', ss = '00'] = matchExif;
      captureTs = `${y}${m}${d}${hh}${mm}${ss}`;
    } else {
      const idMatch = (p.id || '').match(/^(\d{8})/);
      if (idMatch) {
        captureTs = `${idMatch[1]}000000`;
      }
    }

    const animalName = (ai.species_hebrew || p.species_he || ai.title || p.title || '').trim();
    const addedTs = p.processed_at || '';

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
      captureTs,
      animalName,
      addedTs,
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

// Sorting options
const sortOptions = [
  { value: 'capture_desc', label: 'תאריך צילום (מהחדש לישן)' },
  { value: 'capture_asc', label: 'תאריך צילום (מהישן לחדש)' },
  { value: 'animal_asc', label: 'שם החיה (א׳ עד ת׳)' },
  { value: 'animal_desc', label: 'שם החיה (ת׳ עד א׳)' },
  { value: 'added_desc', label: 'תאריך הוספה (מהחדש לישן)' },
  { value: 'added_asc', label: 'תאריך הוספה (מהישן לחדש)' },
];

// Active filter & sort states
const activeCategory = ref('נבחרות ⭐');
const searchQuery = ref('');
const activeTag = ref(null);
const activePhoto = ref(null);
const sortBy = ref('capture_desc');

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

// Filtered photos computed property (category, tag, search query)
const filteredPhotos = computed(() => {
  return normalizedPhotos.value.filter(photo => {
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

// Sorted photos computed property based on selected sortBy
const sortedPhotos = computed(() => {
  const list = [...filteredPhotos.value];
  switch (sortBy.value) {
    case 'capture_desc':
      return list.sort((a, b) => b.captureTs.localeCompare(a.captureTs) || b.id.localeCompare(a.id));
    case 'capture_asc':
      return list.sort((a, b) => a.captureTs.localeCompare(b.captureTs) || a.id.localeCompare(b.id));
    case 'animal_asc':
      return list.sort((a, b) => a.animalName.localeCompare(b.animalName, 'he') || b.captureTs.localeCompare(a.captureTs));
    case 'animal_desc':
      return list.sort((a, b) => b.animalName.localeCompare(a.animalName, 'he') || b.captureTs.localeCompare(a.captureTs));
    case 'added_desc':
      return list.sort((a, b) => (b.addedTs || '').localeCompare(a.addedTs || '') || b.captureTs.localeCompare(a.captureTs));
    case 'added_asc':
      return list.sort((a, b) => (a.addedTs || '').localeCompare(b.addedTs || '') || a.captureTs.localeCompare(b.captureTs));
    default:
      return list;
  }
});

// ==========================================
// Virtual Pagination & Infinite Scroll (Batch of 30)
// ==========================================
const PAGE_SIZE = 30;
const visibleCount = ref(PAGE_SIZE);
const sentinelRef = ref(null);
let observer = null;

// Reset pagination whenever filters or sort change
watch([activeCategory, searchQuery, activeTag, sortBy], () => {
  visibleCount.value = PAGE_SIZE;
});

// Sliced list of photos currently rendered in the DOM
const visiblePhotos = computed(() => {
  return sortedPhotos.value.slice(0, visibleCount.value);
});

const hasMore = computed(() => {
  return visibleCount.value < sortedPhotos.value.length;
});

const loadMore = () => {
  if (hasMore.value) {
    visibleCount.value = Math.min(visibleCount.value + PAGE_SIZE, sortedPhotos.value.length);
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

    // 1. Category
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
      activeCategory.value = 'נבחרות ⭐';
    }

    // 2. Sort option
    const sort = params.get('sort');
    if (sort && sortOptions.some(o => o.value === sort)) {
      sortBy.value = sort;
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
        const idx = sortedPhotos.value.findIndex(p => p.id === match.id);
        if (idx >= visibleCount.value) {
          visibleCount.value = Math.min(idx + PAGE_SIZE, sortedPhotos.value.length);
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

  // Category (omitted when default 'נבחרות ⭐')
  if (activeCategory.value && activeCategory.value !== 'נבחרות ⭐') {
    params.set('category', activeCategory.value);
  } else {
    params.delete('category');
  }

  // Sort option (omitted when default 'capture_desc')
  if (sortBy.value && sortBy.value !== 'capture_desc') {
    params.set('sort', sortBy.value);
  } else {
    params.delete('sort');
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

watch([activeCategory, searchQuery, activeTag, sortBy], () => {
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

const handleSortChange = (newSort) => {
  sortBy.value = newSort;
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
  sortBy.value = 'capture_desc';
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
  const idx = sortedPhotos.value.findIndex(p => p.id === photo.id);
  if (idx >= visibleCount.value) {
    visibleCount.value = Math.min(idx + PAGE_SIZE, sortedPhotos.value.length);
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
      :filteredCount="sortedPhotos.length"
      :totalCount="normalizedPhotos.length"
      :selectedCount="selectedPhotoIds.length"
      :sortBy="sortBy"
      :sortOptions="sortOptions"
      @update:category="handleCategoryChange"
      @update:sort="handleSortChange"
      @update:search="handleSearchChange"
      @update:tag="handleTagChange"
      @reset-filters="resetFilters"
      @open-selection="openSelectionModal"
    />

    <!-- Featured Category Banner -->
    <div
      v-if="activeCategory === 'נבחרות ⭐'"
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
      :photosList="sortedPhotos"
      @close="closePhoto"
      @navigate="navigateToPhoto"
      @select-tag="selectTagFromLightbox"
    />
  </div>
</template>
