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
  Maximize2
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

// Drawer toggle state
const showDrawer = ref(true);
const isHighResLoaded = ref(false);

// Current photo index
const currentIndex = computed(() => {
  if (!props.photo) return -1;
  return props.photosList.findIndex(p => p.id === props.photo.id);
});

const hasNext = computed(() => currentIndex.value < props.photosList.length - 1);
const hasPrev = computed(() => currentIndex.value > 0);

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

// Touch gestures / Swipe support
const touchStartX = ref(0);
const touchStartY = ref(0);

const handleTouchStart = (e) => {
  touchStartX.value = e.changedTouches[0].screenX;
  touchStartY.value = e.changedTouches[0].screenY;
};

const handleTouchEnd = (e) => {
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
    handleClose();
  } else if (e.key === 'ArrowRight') {
    // In RTL, ArrowRight naturally corresponds to backwards/previous or next
    goPrev();
  } else if (e.key === 'ArrowLeft') {
    goNext();
  }
};

watch(() => props.photo, () => {
  isHighResLoaded.value = false;
});

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown);
});

onUnmounted(() => {
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
      <header class="flex items-center justify-between px-4 sm:px-6 py-3.5 z-20 border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
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
      <div class="relative flex-1 flex flex-col lg:flex-row overflow-hidden">
        
        <!-- Large Image Stage -->
        <div class="relative flex-1 flex items-center justify-center p-2 sm:p-6 lg:p-8 min-h-0">
          
          <!-- Navigation Arrow Right (Previous in RTL) -->
          <button
            v-if="hasPrev"
            @click.stop="goPrev"
            class="absolute right-3 sm:right-6 top-1/2 -translate-y-1/2 z-20 p-3 rounded-full bg-slate-900/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-white/10 shadow-xl backdrop-blur-md transition-transform hover:scale-110 active:scale-95 cursor-pointer"
            aria-label="התמונה הקודמת"
          >
            <ChevronRight class="w-6 h-6" />
          </button>

          <!-- Navigation Arrow Left (Next in RTL) -->
          <button
            v-if="hasNext"
            @click.stop="goNext"
            class="absolute left-3 sm:left-6 top-1/2 -translate-y-1/2 z-20 p-3 rounded-full bg-slate-900/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-white/10 shadow-xl backdrop-blur-md transition-transform hover:scale-110 active:scale-95 cursor-pointer"
            aria-label="התמונה הבאה"
          >
            <ChevronLeft class="w-6 h-6" />
          </button>

          <!-- Image Container with Progressive Fade-in -->
          <div class="relative max-w-full max-h-full flex items-center justify-center">
            <!-- Low-res thumbnail placeholder while display image loads -->
            <img
              :src="photo.thumbnail"
              :alt="photo.title"
              class="max-w-full max-h-[80vh] object-contain rounded-xl shadow-2xl filter blur-sm transition-opacity duration-300"
              :class="isHighResLoaded ? 'opacity-0 absolute inset-0' : 'opacity-100'"
            />
            <!-- High-Res Display Image -->
            <img
              :src="photo.display"
              :alt="photo.title"
              @load="isHighResLoaded = true"
              :class="[
                'max-w-full max-h-[80vh] object-contain rounded-xl shadow-2xl transition-opacity duration-500',
                isHighResLoaded ? 'opacity-100' : 'opacity-0'
              ]"
            />
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
            class="w-full lg:w-96 max-h-[45vh] lg:max-h-full overflow-y-auto bg-slate-900/90 border-t lg:border-t-0 lg:border-r border-slate-800/90 backdrop-blur-2xl p-5 sm:p-6 space-y-6 text-right z-30 shadow-2xl"
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
                  <span class="text-slate-400 text-xs font-mono">{{ photo.exif.date }}</span>
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
