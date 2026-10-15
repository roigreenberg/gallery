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
  showCaptions: {
    type: Boolean,
    default: false
  },
  currentLang: {
    type: String,
    default: 'he'
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
        <Camera class="w-8 h-8 stroke-1 text-slate-400" />
      </div>
      <h3 class="text-lg font-semibold text-slate-200 mb-1">
        {{ currentLang === 'en' ? 'No matching photos found' : 'לא נמצאו תמונות תואמות' }}
      </h3>
      <p class="text-sm text-slate-400 max-w-sm mx-auto">
        {{ currentLang === 'en' ? 'Try adjusting your search terms or selecting a different category or tag' : 'נסה לשנות את מילות החיפוש או לבחור קטגוריה ותגית אחרת' }}
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
        :class="selectedIds.includes(photo.id) ? 'border-sky-500/80 ring-2 ring-sky-500/30 shadow-sky-500/10' : 'border-slate-800/80 hover:border-slate-700/80'"
        style="content-visibility: auto; contain-intrinsic-size: auto 300px;"
        @click="emit('select-photo', photo)"
      >
        <!-- Selection Checkbox Button -->
        <button
          type="button"
          @click.stop="emit('toggle-select', photo)"
          class="absolute z-20 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer shadow-lg"
          :class="[
            currentLang === 'en' ? 'top-3 right-3' : 'top-3 left-3',
            selectedIds.includes(photo.id) ? 'bg-sky-500 text-slate-950 font-black scale-105 ring-2 ring-white/60' : 'bg-slate-950/70 hover:bg-slate-900 text-slate-300 hover:text-white border border-white/20 opacity-80 group-hover:opacity-100 hover:scale-110'
          ]"
          :title="currentLang === 'en'
            ? (selectedIds.includes(photo.id) ? 'Remove from selection' : 'Add to selection')
            : (selectedIds.includes(photo.id) ? 'הסר מרשימת הבחירה' : 'הוסף לרשימת הבחירה')"
          :aria-label="currentLang === 'en' ? 'Select photo' : 'בחר תמונה'"
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
            :alt="currentLang === 'en' ? (photo.title_en || photo.title) : photo.title"
            loading="lazy"
            decoding="async"
            class="w-full h-full object-cover transform transition-transform duration-500 group-hover:scale-105"
          />

          <!-- Bottom Humorous Caption Overlay (visible directly on image when 'showCaptions' is ON) -->
          <Transition
            enter-active-class="transition duration-200 ease-out"
            enter-from-class="opacity-0 translate-y-2"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition duration-150 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 translate-y-2"
          >
            <div
              v-if="showCaptions && (currentLang === 'en' ? (photo.humorous_description_en || photo.humorous_description) : photo.humorous_description)"
              class="absolute bottom-0 inset-x-0 z-10 p-2.5 sm:p-3 bg-gradient-to-t from-slate-950/95 via-slate-950/75 to-transparent backdrop-blur-[2px] pointer-events-none"
            >
              <p
                class="text-xs sm:text-[13px] font-medium text-amber-100/95 leading-snug drop-shadow-md line-clamp-3"
                :class="currentLang === 'en' ? 'text-left' : 'text-right'"
              >
                <span class="text-sm select-none align-baseline" :class="currentLang === 'en' ? 'mr-1' : 'ml-1'">🎭</span>
                <span class="italic font-semibold align-baseline">"{{ currentLang === 'en' ? (photo.humorous_description_en || photo.humorous_description) : photo.humorous_description }}"</span>
              </p>
            </div>
          </Transition>
        </div>

        <!-- Top Badges: Featured Star, Name badge (if exists), and Category -->
        <div
          class="absolute z-10 flex items-center gap-1.5 transition-transform duration-300 group-hover:-translate-y-0.5 max-w-[calc(100%-80px)] overflow-hidden"
          :class="currentLang === 'en' ? 'top-3 left-3' : 'top-3 right-3'"
        >
          <span
            v-if="photo.is_featured"
            class="px-2 py-0.5 text-[11px] font-bold text-amber-300 bg-amber-950/80 backdrop-blur-md rounded-full border border-amber-500/50 shadow-sm shrink-0"
            :title="currentLang === 'en' ? 'Featured photo' : 'תמונה נבחרת'"
          >
            ⭐
          </span>
          <!-- Subject / Species Name badge before Category badge -->
          <span
            v-if="currentLang === 'en' ? (photo.species_en || photo.species_la || photo.species_he) : photo.species_he"
            class="inline-block px-2.5 py-1 text-[11px] font-bold tracking-tight text-white bg-slate-950/85 backdrop-blur-md rounded-full border border-sky-500/40 shadow-sm truncate max-w-[140px]"
            :title="currentLang === 'en' ? (photo.species_en || photo.species_he) : photo.species_he"
          >
            {{ currentLang === 'en' ? (photo.species_en || photo.species_la || photo.species_he) : photo.species_he }}
          </span>
          <!-- Category badge -->
          <span class="inline-block px-2.5 py-1 text-[11px] font-medium tracking-wide text-slate-200 bg-slate-950/75 backdrop-blur-md rounded-full border border-white/10 shadow-sm shrink-0">
            {{ currentLang === 'en' ? (photo.categoryEn || photo.category) : (photo.categoryHe || photo.category) }}
          </span>
        </div>

        <!-- Hover Overlay Details (Always visible on mobile or smoothly revealed on hover) -->
        <div
          class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-5 pointer-events-none"
        >
          <div
            class="transform translate-y-2 group-hover:translate-y-0 transition-transform duration-300 space-y-1.5"
            :class="currentLang === 'en' ? 'text-left' : 'text-right'"
          >
            <h4 class="text-base font-bold text-white tracking-tight drop-shadow-sm">
              {{ currentLang === 'en' ? (photo.title_en || photo.title) : photo.title }}
            </h4>

            <p class="text-xs text-sky-300/90 font-medium italic">
              {{ currentLang === 'en' ? (photo.species_en || photo.species_la || photo.species_he) : photo.species_he }}
              <span v-if="photo.species_la && currentLang !== 'en'" class="text-slate-400 font-normal">({{ photo.species_la }})</span>
            </p>

            <!-- Humorous description in hover overlay if present -->
            <p
              v-if="currentLang === 'en' ? (photo.humorous_description_en || photo.humorous_description) : photo.humorous_description"
              class="text-xs text-amber-200/90 italic pt-1 truncate border-t border-white/10"
              :title="currentLang === 'en' ? (photo.humorous_description_en || photo.humorous_description) : photo.humorous_description"
            >
              <span :class="currentLang === 'en' ? 'mr-1' : 'ml-1'">🎭</span>"{{ currentLang === 'en' ? (photo.humorous_description_en || photo.humorous_description) : photo.humorous_description }}"
            </p>

            <!-- Quick EXIF Badge -->
            <div class="pt-2 flex items-center justify-between text-[11px] text-slate-300/80 border-t border-white/10">
              <span class="truncate max-w-[170px]">
                {{ photo.exif.camera }}
              </span>
              <span class="flex items-center gap-1 text-sky-400">
                <Eye class="w-3.5 h-3.5" />
                <span>{{ currentLang === 'en' ? 'Zoom' : 'הגדלה' }}</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
