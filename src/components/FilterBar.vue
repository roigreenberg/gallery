<script setup>
import { computed } from 'vue';
import { Search, X, Sparkles, ArrowUpDown, ChevronDown } from 'lucide-vue-next';

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
  },
  sortBy: {
    type: String,
    default: 'capture_desc'
  },
  sortOptions: {
    type: Array,
    required: true
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

const emit = defineEmits(['update:category', 'update:search', 'update:tag', 'update:sort', 'toggle-captions', 'toggle-lang', 'reset-filters', 'open-selection']);

const hasActiveFilters = computed(() => {
  const isDefaultCategory = props.activeCategory === 'נבחרות ⭐' || props.activeCategory === 'featured' || props.activeCategory === 'Featured ⭐';
  return !isDefaultCategory || props.searchQuery.trim() !== '' || Boolean(props.activeTag) || props.sortBy !== 'capture_desc';
});
</script>

<template>
  <section class="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
    <!-- Top Filter Row: Search & Category Actions -->
    <div class="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
      
      <!-- Search Input -->
      <div class="relative flex-1 max-w-md">
        <div
          class="absolute inset-y-0 flex items-center pointer-events-none text-slate-400"
          :class="currentLang === 'en' ? 'left-0 pl-3.5' : 'right-0 pr-3.5'"
        >
          <Search class="w-4 h-4" />
        </div>
        <input
          type="text"
          :value="searchQuery"
          @input="emit('update:search', $event.target.value)"
          :placeholder="currentLang === 'en' ? 'Search by species, title, gear (Canon, Lens, ISO)...' : 'חיפוש לפי מין, כותרת, ציוד (Canon, Lens, ISO)...'"
          :class="currentLang === 'en' ? 'pl-10 pr-10' : 'pr-10 pl-10'"
          class="w-full py-2.5 rounded-full bg-slate-900/80 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition shadow-inner backdrop-blur-md"
        />
        <button
          v-if="searchQuery"
          @click="emit('update:search', '')"
          class="absolute inset-y-0 flex items-center text-slate-400 hover:text-slate-200 transition cursor-pointer"
          :class="currentLang === 'en' ? 'right-0 pr-3' : 'left-0 pl-3'"
          :aria-label="currentLang === 'en' ? 'Clear search' : 'נקה חיפוש'"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Result Counter & Actions -->
      <div class="flex items-center justify-between md:justify-end gap-2.5 sm:gap-3 text-xs sm:text-sm text-slate-400 flex-wrap">
        <!-- Results Counter -->
        <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900/60 border border-slate-800">
          <span class="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
          <template v-if="currentLang === 'en'">
            <span>Showing </span>
            <strong class="text-sky-300 font-semibold">{{ filteredCount }}</strong>
            <span> of </span>
            <span>{{ totalCount }} photos</span>
          </template>
          <template v-else>
            <span>מוצגות </span>
            <strong class="text-sky-300 font-semibold">{{ filteredCount }}</strong>
            <span> מתוך </span>
            <span>{{ totalCount }} תמונות</span>
          </template>
        </div>

        <!-- Language Toggle Button (EN ⇄ עב) -->
        <button
          type="button"
          @click="emit('toggle-lang')"
          class="px-3 py-1.5 rounded-full border transition-all duration-200 text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-sm active:scale-95 select-none bg-slate-900/70 border-slate-700/90 text-sky-400 hover:text-white hover:bg-slate-800"
          :title="currentLang === 'en' ? 'החלף את שפת האתר לעברית' : 'Switch website language to English'"
        >
          <span class="text-sm">🌐</span>
          <span>{{ currentLang === 'en' ? 'עברית (HE)' : 'English (EN)' }}</span>
        </button>

        <!-- "אני לא פולני" / Humor Mode Toggle Button -->
        <button
          type="button"
          @click="emit('toggle-captions')"
          class="px-3.5 py-1.5 rounded-full border transition-all duration-200 text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-sm active:scale-95 select-none"
          :class="showCaptions
            ? 'bg-gradient-to-r from-amber-500/25 via-purple-500/25 to-pink-500/20 border-amber-400 text-amber-200 ring-2 ring-amber-400/40 shadow-amber-500/20 font-bold scale-102'
            : 'bg-slate-900/60 border-slate-800 text-slate-300 hover:text-amber-300 hover:border-slate-700 hover:bg-slate-800/80'"
          :title="currentLang === 'en'
            ? (showCaptions ? 'Hide humorous captions from gallery photos' : 'Show humorous captions directly on gallery photos')
            : (showCaptions ? 'הסתר את המשפטים המשעשעים שעל גבי התמונות' : 'הצג את המשפטים המשעשעים ישירות על גבי התמונות בגלריה')"
        >
          <span class="text-sm">🎭</span>
          <span>{{ currentLang === 'en' ? 'Humor Mode' : 'אני לא פולני' }}</span>
        </button>

        <!-- Sort Selector -->
        <div class="relative inline-flex items-center">
          <div
            class="absolute inset-y-0 flex items-center pointer-events-none text-sky-400"
            :class="currentLang === 'en' ? 'left-0 pl-3' : 'right-0 pr-3'"
          >
            <ArrowUpDown class="w-3.5 h-3.5" />
          </div>
          <select
            :value="sortBy"
            @change="emit('update:sort', $event.target.value)"
            class="appearance-none bg-slate-900/80 hover:bg-slate-800 text-slate-200 hover:text-white border border-slate-700/80 hover:border-slate-600 rounded-full py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-sky-500/50 cursor-pointer transition shadow-inner backdrop-blur-md"
            :class="currentLang === 'en' ? 'pl-8 pr-7' : 'pr-8 pl-7'"
            :title="currentLang === 'en' ? 'Sort photos' : 'סדר מיון התמונות'"
          >
            <option
              v-for="opt in sortOptions"
              :key="opt.value"
              :value="opt.value"
              class="bg-slate-900 text-slate-200 py-1"
            >
              {{ opt.label }}
            </option>
          </select>
          <div
            class="absolute inset-y-0 flex items-center pointer-events-none text-slate-400"
            :class="currentLang === 'en' ? 'right-0 pr-2.5' : 'left-0 pl-2.5'"
          >
            <ChevronDown class="w-3 h-3" />
          </div>
        </div>

        <!-- Chosen Photos Button -->
        <button
          type="button"
          @click="emit('open-selection')"
          class="px-3.5 py-1.5 rounded-full border transition text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-sm"
          :class="selectedCount > 0 ? 'bg-sky-950 border-sky-500 text-sky-300 ring-1 ring-sky-500/40 shadow-sky-500/10' : 'bg-slate-900/60 border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800'"
        >
          <span>{{ currentLang === 'en' ? '📋 My Selection' : '📋 תמונות שבחרתי' }}</span>
          <span
            v-if="selectedCount > 0"
            class="px-1.5 py-0.2 rounded-full bg-sky-500 text-slate-950 text-[10px] font-black"
          >
            {{ selectedCount }}
          </span>
        </button>

        <!-- Reset Filters -->
        <button
          v-if="hasActiveFilters"
          @click="emit('reset-filters')"
          class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 transition cursor-pointer"
        >
          <X class="w-3 h-3" />
          <span>{{ currentLang === 'en' ? 'Reset filters' : 'איפוס סינון' }}</span>
        </button>
      </div>
    </div>

    <!-- Category Pills -->
    <div class="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none no-scrollbar">
      <button
        v-for="cat in categories"
        :key="typeof cat === 'object' ? cat.key : cat"
        @click="emit('update:category', typeof cat === 'object' ? cat.key : cat)"
        :class="[
          'px-4 py-2 rounded-full text-xs sm:text-sm font-medium tracking-wide transition-all duration-200 whitespace-nowrap cursor-pointer select-none',
          (activeCategory === (typeof cat === 'object' ? cat.key : cat) || activeCategory === (typeof cat === 'object' ? cat.label : cat))
            ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/25 ring-2 ring-sky-400/40 font-semibold scale-102'
            : 'bg-slate-900/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800/80'
        ]"
      >
        {{ typeof cat === 'object' ? cat.label : cat }}
      </button>
    </div>

    <!-- Quick Tags Chips -->
    <div class="flex items-center gap-2 flex-wrap text-xs pt-1">
      <div
        class="flex items-center gap-1 text-slate-400 font-medium"
        :class="currentLang === 'en' ? 'mr-1' : 'ml-1'"
      >
        <Sparkles class="w-3.5 h-3.5 text-amber-400" />
        <span>{{ currentLang === 'en' ? 'Quick Tags:' : 'תגיות מהירות:' }}</span>
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
