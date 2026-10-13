<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import FilterBar from './FilterBar.vue';
import GalleryGrid from './GalleryGrid.vue';
import Lightbox from './Lightbox.vue';

const props = defineProps({
  initialPhotos: {
    type: Array,
    required: true
  }
});

// Category mapping: Normalize English categories to Hebrew UI labels
// Note: Moon and night sky photos are categorized under 'נוף' (Landscape)
const categoryMap = {
  'wildlife': 'טבע וציפורים',
  'landscape': 'נוף',
  'astrophotography': 'נוף',
  'macro': 'מאקרו',
  'nature': 'טבע וציפורים',
  'portrait': 'טבע וציפורים',
  'other': 'נוף'
};

const getCategoryHebrew = (cat) => {
  return categoryMap[cat] || cat || 'טבע וציפורים';
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
    const allPhotoTags = Array.from(new Set([...tags, ...behavior]))
      .filter(Boolean)
      .filter(t => !t.includes('אסטרונומ'));

    return {
      id: p.id || p.filename || String(Math.random()),
      title: ai.title || p.title || p.filename || 'תמונת טבע',
      species_he: ai.species_hebrew || p.species_he || '',
      species_la: ai.species_latin || p.species_la || '',
      category: getCategoryHebrew(ai.category || p.category),
      description: ai.description || p.description || '',
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
        date: exif.date_time_original || exif.date || '',
        location: exif.location || ''
      }
    };
  });
});

// Categories list in UI (Astrophotography removed)
const categories = ['הכל', 'טבע וציפורים', 'נוף', 'מאקרו'];

// Active filter states
const activeCategory = ref('הכל');
const searchQuery = ref('');
const activeTag = ref(null);
const activePhoto = ref(null);

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
    // 1. Category check
    if (activeCategory.value !== 'הכל' && photo.category !== activeCategory.value) {
      return false;
    }

    // 2. Tag check
    if (activeTag.value && !(photo.tags || []).includes(activeTag.value)) {
      return false;
    }

    // 3. Search query check (Hebrew species, Latin species, title, camera, lens, tags)
    const q = searchQuery.value.trim().toLowerCase();
    if (q) {
      const matchTitle = photo.title?.toLowerCase().includes(q);
      const matchSpeciesHe = photo.species_he?.toLowerCase().includes(q);
      const matchSpeciesLa = photo.species_la?.toLowerCase().includes(q);
      const matchCamera = photo.exif?.camera?.toLowerCase().includes(q);
      const matchLens = photo.exif?.lens?.toLowerCase().includes(q);
      const matchTags = (photo.tags || []).some(t => t.toLowerCase().includes(q));

      if (!matchTitle && !matchSpeciesHe && !matchSpeciesLa && !matchCamera && !matchLens && !matchTags) {
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

// Reset pagination whenever filters change
watch([activeCategory, searchQuery, activeTag], () => {
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

onMounted(() => {
  setupObserver();
});

watch(sentinelRef, () => {
  setupObserver();
});

onUnmounted(() => {
  if (observer) {
    observer.disconnect();
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
  activeCategory.value = 'הכל';
  searchQuery.value = '';
  activeTag.value = null;
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
      @update:category="handleCategoryChange"
      @update:search="handleSearchChange"
      @update:tag="handleTagChange"
      @reset-filters="resetFilters"
    />

    <!-- Masonry Grid with paged visible items -->
    <GalleryGrid
      :photos="visiblePhotos"
      @select-photo="openPhoto"
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

    <!-- Lightbox Modal -->
    <Lightbox
      :photo="activePhoto"
      :photosList="filteredPhotos"
      @close="closePhoto"
      @navigate="navigateToPhoto"
      @select-tag="selectTagFromLightbox"
    />
  </div>
</template>
