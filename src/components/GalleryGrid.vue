<script setup>
import { ref } from 'vue';
import { Camera, Eye, Tag } from 'lucide-vue-next';

const props = defineProps({
  photos: {
    type: Array,
    required: true
  }
});

const emit = defineEmits(['select-photo']);

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
        <Camera class="w-8 h-8 stroke-1 text-slate-400" />
      </div>
      <h3 class="text-lg font-semibold text-slate-200 mb-1">לא נמצאו תמונות תואמות</h3>
      <p class="text-sm text-slate-400 max-w-sm mx-auto">
        נסה לשנות את מילות החיפוש או לבחור קטגוריה ותגית אחרת
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
        class="break-inside-avoid group relative rounded-2xl overflow-hidden bg-slate-900 border border-slate-800/80 shadow-lg hover:shadow-2xl hover:border-slate-700/80 transition-all duration-300 cursor-pointer"
        style="content-visibility: auto; contain-intrinsic-size: auto 300px;"
        @click="emit('select-photo', photo)"
      >
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

        <!-- Subtle Top Badge: Category -->
        <div class="absolute top-3 right-3 z-10 transition-transform duration-300 group-hover:-translate-y-0.5">
          <span class="inline-block px-2.5 py-1 text-[11px] font-medium tracking-wide text-slate-200 bg-slate-950/75 backdrop-blur-md rounded-full border border-white/10 shadow-sm">
            {{ photo.category }}
          </span>
        </div>

        <!-- Hover Overlay Details (Always visible on mobile or smoothly revealed on hover) -->
        <div
          class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-5 pointer-events-none"
        >
          <div class="transform translate-y-2 group-hover:translate-y-0 transition-transform duration-300 space-y-1.5 text-right">
            <h4 class="text-base font-bold text-white tracking-tight drop-shadow-sm">
              {{ photo.title }}
            </h4>

            <p class="text-xs text-sky-300/90 font-medium italic">
              {{ photo.species_he }}
              <span v-if="photo.species_la" class="text-slate-400 font-normal">({{ photo.species_la }})</span>
            </p>

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
