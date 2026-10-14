<script setup>
import { ref } from 'vue';
import { Camera, Eye, Tag } from 'lucide-vue-next';

const props = defineProps({
  photos: {
    type: Array,
    required: true
  },
  selectedIds: {
    type: Array,
    default: () => []
  },
  isHumorMode: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['select-photo', 'toggle-select']);

// Track loaded state of thumbnails for smooth fade-in
const loadedMap = ref({});

const handleImageLoad = (id) => {
  loadedMap.value[id] = true;
};
</script>

<template>
  <div class="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
    <!-- Empty State -->
    <div
      v-if="photos.length === 0"
      class="text-center py-24 px-4 rounded-3xl border border-dashed border-slate-800 bg-slate-900/30"
    >
      <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 text-slate-400 mb-4">
        <span v-if="isHumorMode" class="text-3xl">🎭</span>
        <Camera v-else class="w-8 h-8 stroke-1 text-slate-400" />
      </div>
      <h3 class="text-lg font-semibold text-slate-200 mb-1">
        {{ isHumorMode ? 'אין תמונות במצב הומוריסטי כרגע' : 'לא נמצאו תמונות תואמות' }}
      </h3>
      <p class="text-sm text-slate-400 max-w-md mx-auto">
        <span v-if="isHumorMode">
          התיאורים ההומוריסטיים נמצאים בתהליך ניתוח והפקה ע"י ה-AI. ברגע שנוספו תיאורים שנונים לתמונות, הן תופענה כאן אוטומטית.
        </span>
        <span v-else>
          נסה לשנות את מילות החיפוש או לבחור קטגוריה ותגית אחרת
        </span>
      </p>
    </div>

    <!-- Responsive Multi-Column Masonry Grid -->
    <div
      v-else
      class="columns-1 sm:columns-2 lg:columns-3 xl:columns-3 gap-6 space-y-6"
    >
      <div
        v-for="photo in photos"
        :key="photo.id"
        class="break-inside-avoid group relative rounded-2xl overflow-hidden bg-slate-900 border transition-all duration-300 cursor-pointer shadow-lg hover:shadow-2xl"
        :class="selectedIds.includes(photo.id) ? 'border-sky-500/80 ring-2 ring-sky-500/30 shadow-sky-500/10' : (isHumorMode ? 'border-amber-500/30 hover:border-amber-400/60' : 'border-slate-800/80 hover:border-slate-700/80')"
        style="content-visibility: auto; contain-intrinsic-size: auto 300px;"
        @click="emit('select-photo', photo)"
      >
        <!-- Selection Checkbox Button -->
        <button
          type="button"
          @click.stop="emit('toggle-select', photo)"
          class="absolute top-3 left-3 z-20 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer shadow-lg"
          :class="selectedIds.includes(photo.id) ? 'bg-sky-500 text-slate-950 font-black scale-105 ring-2 ring-white/60' : 'bg-slate-950/70 hover:bg-slate-900 text-slate-300 hover:text-white border border-white/20 opacity-80 group-hover:opacity-100 hover:scale-110'"
          :title="selectedIds.includes(photo.id) ? 'הסר מרשימת הבחירה' : 'הוסף לרשימת הבחירה'"
          aria-label="בחר תמונה"
        >
          <span v-if="selectedIds.includes(photo.id)" class="text-xs">✓</span>
          <span v-else class="text-xs">+</span>
        </button>

        <!-- Skeleton / placeholder loader background with preserved aspect ratio -->
        <div
          class="w-full relative overflow-hidden bg-slate-950"
          :style="{ aspectRatio: photo.aspectRatio || '3/2' }"
        >
          <!-- Image with lazy loading and fade-in -->
          <img
            :src="photo.thumbnail"
            :alt="photo.title"
            loading="lazy"
            decoding="async"
            class="w-full h-full object-cover transform transition-transform duration-500 group-hover:scale-105"
          />
        </div>

        <!-- Top Badges: Category & Featured Star & Humor -->
        <div class="absolute top-3 right-3 z-10 flex items-center gap-1.5 transition-transform duration-300 group-hover:-translate-y-0.5">
          <span
            v-if="isHumorMode && photo.humorous_description"
            class="px-2 py-0.5 text-[11px] font-bold text-amber-200 bg-purple-950/90 backdrop-blur-md rounded-full border border-amber-400/50 shadow-sm"
            title="מצב הומוריסטי"
          >
            🎭
          </span>
          <span
            v-if="photo.is_featured"
            class="px-2 py-0.5 text-[11px] font-bold text-amber-300 bg-amber-950/80 backdrop-blur-md rounded-full border border-amber-500/50 shadow-sm"
            title="תמונה נבחרת"
          >
            ⭐
          </span>
          <span class="inline-block px-2.5 py-1 text-[11px] font-medium tracking-wide text-slate-200 bg-slate-950/75 backdrop-blur-md rounded-full border border-white/10 shadow-sm">
            {{ photo.category }}
          </span>
        </div>

        <!-- Hover Overlay Details (Always visible on mobile or smoothly revealed on hover) -->
        <div
          class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-5 pointer-events-none"
        >
          <div class="transform translate-y-2 group-hover:translate-y-0 transition-transform duration-300 space-y-1.5 text-right">
            <!-- Humorous caption if in humor mode -->
            <div v-if="isHumorMode && photo.humorous_description" class="space-y-1">
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-[10px] font-bold border border-amber-500/30">
                <span>🎭</span>
                <span>זווית משעשעת</span>
              </span>
              <p class="text-sm font-bold text-amber-100 italic leading-snug drop-shadow-md">
                "{{ photo.humorous_description }}"
              </p>
              <p class="text-[11px] text-slate-300/80 truncate font-normal">
                {{ photo.title }}
              </p>
            </div>

            <!-- Standard title and species -->
            <div v-else class="space-y-1">
              <h4 class="text-base font-bold text-white tracking-tight drop-shadow-sm">
                {{ photo.title }}
              </h4>

              <p class="text-xs text-sky-300/90 font-medium italic">
                {{ photo.species_he }}
                <span v-if="photo.species_la" class="text-slate-400 font-normal">({{ photo.species_la }})</span>
              </p>
            </div>

            <!-- Quick EXIF Badge -->
            <div class="pt-2 flex items-center justify-between text-[11px] text-slate-300/80 border-t border-white/10">
              <span class="truncate max-w-[170px]">
                {{ photo.exif.camera }}
              </span>
              <span class="flex items-center gap-1 text-sky-400">
                <Eye class="w-3.5 h-3.5" />
                <span>הגדלה</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
