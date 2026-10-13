<script setup>
import { computed } from 'vue';
import { Search, X, SlidersHorizontal, Sparkles } from 'lucide-vue-next';

const props = defineProps({
  categories: {
    type: Array,
    required: true
  },
  activeCategory: {
    type: String,
    required: true
  },
  searchQuery: {
    type: String,
    required: true
  },
  allTags: {
    type: Array,
    required: true
  },
  activeTag: {
    type: String,
    default: null
  },
  filteredCount: {
    type: Number,
    required: true
  },
  totalCount: {
    type: Number,
    required: true
  },
  selectedCount: {
    type: Number,
    default: 0
  }
});

const emit = defineEmits(['update:category', 'update:search', 'update:tag', 'reset-filters', 'open-selection']);

const hasActiveFilters = computed(() => {
  return props.activeCategory !== 'הכל' || props.searchQuery.trim() !== '' || Boolean(props.activeTag);
});
</script>

<template>
  <section class="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
    <!-- Top Filter Row: Search & Category Pills -->
    <div class="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
      
      <!-- Search Input -->
      <div class="relative flex-1 max-w-md">
        <div class="absolute inset-y-0 right-0 pr-3.5 flex items-center pointer-events-none text-slate-400">
          <Search class="w-4 h-4" />
        </div>
        <input
          type="text"
          :value="searchQuery"
          @input="emit('update:search', $event.target.value)"
          placeholder="חיפוש לפי מין, כותרת, ציוד (Sony, Lens, ISO)..."
          class="w-full pl-10 pr-10 py-2.5 rounded-full bg-slate-900/80 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition shadow-inner backdrop-blur-md"
        />
        <button
          v-if="searchQuery"
          @click="emit('update:search', '')"
          class="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 hover:text-slate-200 transition"
          aria-label="נקה חיפוש"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Result Counter & Clear & Selection Action -->
      <div class="flex items-center justify-between md:justify-end gap-3 text-xs sm:text-sm text-slate-400 flex-wrap">
        <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900/60 border border-slate-800">
          <span class="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
          <span>מוצגות </span>
          <strong class="text-sky-300 font-semibold">{{ filteredCount }}</strong>
          <span> מתוך </span>
          <span>{{ totalCount }} תמונות</span>
        </div>

        <!-- Chosen Photos Button -->
        <button
          type="button"
          @click="emit('open-selection')"
          class="px-3.5 py-1.5 rounded-full border transition text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-sm"
          :class="selectedCount > 0 ? 'bg-sky-950 border-sky-500 text-sky-300 ring-1 ring-sky-500/40 shadow-sky-500/10' : 'bg-slate-900/60 border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800'"
        >
          <span>📋 תמונות שבחרתי</span>
          <span
            v-if="selectedCount > 0"
            class="px-1.5 py-0.2 rounded-full bg-sky-500 text-slate-950 text-[10px] font-black"
          >
            {{ selectedCount }}
          </span>
        </button>

        <button
          v-if="hasActiveFilters"
          @click="emit('reset-filters')"
          class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 transition"
        >
          <X class="w-3 h-3" />
          <span>איפוס סינון</span>
        </button>
      </div>
    </div>

    <!-- Category Pills -->
    <div class="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none no-scrollbar">
      <button
        v-for="cat in categories"
        :key="cat"
        @click="emit('update:category', cat)"
        :class="[
          'px-4 py-2 rounded-full text-xs sm:text-sm font-medium tracking-wide transition-all duration-200 whitespace-nowrap cursor-pointer select-none',
          activeCategory === cat
            ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/25 ring-2 ring-sky-400/40 font-semibold scale-102'
            : 'bg-slate-900/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800/80'
        ]"
      >
        {{ cat }}
      </button>
    </div>

    <!-- Quick Tags Chips -->
    <div class="flex items-center gap-2 flex-wrap text-xs pt-1">
      <div class="flex items-center gap-1 text-slate-400 font-medium ml-1">
        <Sparkles class="w-3.5 h-3.5 text-amber-400" />
        <span>תגיות מהירות:</span>
      </div>
      <button
        v-for="tag in allTags"
        :key="tag"
        @click="emit('update:tag', activeTag === tag ? null : tag)"
        :class="[
          'px-2.5 py-1 rounded-md transition duration-150 cursor-pointer select-none border',
          activeTag === tag
            ? 'bg-sky-950/80 text-sky-300 border-sky-600/60 font-medium'
            : 'bg-slate-900/40 text-slate-400 hover:text-slate-200 border-slate-800 hover:border-slate-700'
        ]"
      >
        #{{ tag }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
