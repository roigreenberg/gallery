<script setup>
import { computed } from 'vue';

const props = defineProps({
  group: {
    type: Object,
    required: true
  },
  photos: {
    type: Array,
    default: () => []
  },
  winner: {
    type: Object,
    default: null
  },
  column: {
    type: String,
    required: true // 'sure' | 'maybe' | 'pool' | 'rejected'
  },
  isOwner: {
    type: Boolean,
    default: false
  },
  currentUser: {
    type: Object,
    default: null
  }
});

const emit = defineEmits([
  'preview',
  'open-decision',
  'select-winner',
  'clear-winner',
  'compare-ai',
  'move-status',
  'drag-start',
  'vote',
  'toggle-area'
]);

const calculateScore = (votes = {}) => {
  let score = 0;
  for (const uid in votes) {
    score += (votes[uid]?.score || 0);
  }
  return score;
};

const countVotes = (votes = {}) => {
  return Object.keys(votes || {}).length;
};

const handleDrag = (e) => {
  if (props.isOwner) {
    emit('drag-start', e, props.group.id);
  }
};
</script>

<template>
  <div
    class="group/card bg-gradient-to-b from-purple-950/30 via-slate-950 to-slate-950 border border-purple-500/40 hover:border-purple-400/90 rounded-xl p-3 space-y-2.5 transition shadow-lg relative"
    :draggable="isOwner"
    @dragstart="handleDrag"
  >
    <!-- Card Header: Title & Group Badge -->
    <div class="flex items-center justify-between gap-1.5 pb-1 border-b border-purple-500/20">
      <div class="flex items-center gap-1.5 min-w-0">
        <span class="text-xs">⚔️</span>
        <h4 class="text-xs font-bold text-purple-200 truncate" :title="group.name">
          {{ group.name }}
        </h4>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <!-- Area Badge if confirmed in Sure -->
        <span
          v-if="column === 'sure'"
          class="px-1.5 py-0.2 rounded text-[9px] font-bold"
          :class="(group.area || 'exhibition') === 'wall' ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/30' : 'bg-indigo-950 text-indigo-300 border border-indigo-500/30'"
        >
          {{ (group.area || 'exhibition') === 'wall' ? '🧱 קיר' : '🖼️ תערוכה' }}
        </span>
        <span
          class="px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 transition"
          :class="winner ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40' : 'bg-purple-900/60 text-purple-300 border border-purple-500/30'"
        >
          {{ winner ? '✓ הוכרע' : `${photos.length} אופציות` }}
        </span>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- CASE A: DECIDED - Large Winner Photo + Alternatives Bar  -->
    <!-- ======================================================== -->
    <template v-if="winner">
      <div
        class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer group/media"
        @click="emit('preview', winner.photo_data)"
      >
        <img
          :src="winner.photo_data?.thumbnail || winner.photo_data?.display"
          class="w-full h-full object-cover group-hover/media:scale-105 transition duration-300"
        />

        <!-- Top Right: Species Badge -->
        <span class="absolute top-2 right-2 px-2 py-0.5 bg-slate-950/80 backdrop-blur-md rounded-full text-[10px] text-purple-300 border border-purple-500/40 font-bold">
          {{ winner.photo_data?.species_he || 'תמונה' }}
        </span>

        <!-- Top Left: Decision Crown Badge -->
        <span class="absolute top-2 left-2 px-2 py-0.5 bg-amber-500 text-slate-950 font-black rounded-full text-[10px] shadow-lg flex items-center gap-1">
          <span>👑 נבחרה מתוך {{ photos.length }}</span>
        </span>

        <!-- Bottom Left: Score Badge -->
        <span
          class="absolute bottom-2 left-2 px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1 shadow-md bg-slate-900/90 text-slate-200 border border-slate-700"
        >
          <span>ציון:</span>
          <span class="font-mono">{{ calculateScore(winner.votes) }}</span>
        </span>
      </div>

      <!-- Title & EXIF -->
      <div>
        <h4 class="text-xs font-bold text-slate-100 truncate">
          {{ winner.photo_data?.title }}
        </h4>
        <p class="text-[10px] text-slate-400 truncate">
          {{ winner.photo_data?.exif?.camera_model }} • {{ winner.photo_data?.exif?.lens_model }}
        </p>
      </div>

      <!-- Alternatives Quick Switcher Strip (חיווי שיש עוד אופציות + החלפה מהירה) -->
      <div class="bg-purple-950/40 border border-purple-500/30 rounded-lg p-1.5 flex items-center justify-between gap-2">
        <div class="flex items-center gap-1 overflow-x-auto py-0.5 min-w-0">
          <span class="text-[10px] text-purple-300 shrink-0 font-medium">אופציות:</span>
          <button
            v-for="alt in photos"
            :key="alt.id"
            type="button"
            @click.stop="emit('select-winner', { group, photo: alt })"
            class="relative w-7 h-7 rounded overflow-hidden border shrink-0 transition cursor-pointer"
            :class="winner.id === alt.id ? 'border-amber-400 ring-2 ring-amber-400/50 scale-105' : 'border-slate-700 opacity-60 hover:opacity-100'"
            :title="alt.photo_data?.title + (winner.id === alt.id ? ' (נבחרה כרגע)' : ' (לחץ להחלפה לזו)')"
          >
            <img :src="alt.photo_data?.thumbnail" class="w-full h-full object-cover" />
            <span v-if="winner.id === alt.id" class="absolute inset-0 bg-amber-500/30 flex items-center justify-center text-[9px] font-black text-amber-300">✓</span>
          </button>
        </div>

        <div class="flex items-center gap-1 shrink-0">
          <button
            type="button"
            @click.stop="emit('open-decision', group)"
            class="px-2 py-0.5 bg-purple-600/40 hover:bg-purple-600 text-purple-200 border border-purple-500/40 rounded text-[10px] font-medium transition cursor-pointer"
            title="פתח השוואה מלאה ובחירה"
          >
            🔄 החלף
          </button>
          <button
            v-if="isOwner"
            type="button"
            @click.stop="emit('clear-winner', group)"
            class="p-0.5 text-slate-400 hover:text-rose-300 transition cursor-pointer text-[10px]"
            title="בטל הכרעה (חזור להתלבטות)"
          >
            ↩
          </button>
        </div>
      </div>

      <!-- Voting Bar on Winner Photo -->
      <div class="flex items-center justify-between bg-slate-900/80 p-1.5 rounded-lg border border-slate-800 text-xs">
        <button
          type="button"
          @click="emit('vote', winner.id, 2)"
          class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
          :class="{ 'ring-1 ring-amber-400 bg-amber-500/20': currentUser && winner.votes?.[currentUser.uid]?.score === 2 }"
          title="🔥 חובה בתערוכה (+2)"
        >
          🔥
        </button>
        <button
          type="button"
          @click="emit('vote', winner.id, 1)"
          class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
          :class="{ 'ring-1 ring-emerald-400 bg-emerald-500/20': currentUser && winner.votes?.[currentUser.uid]?.score === 1 }"
          title="👍 מוצלחת מאוד (+1)"
        >
          👍
        </button>
        <button
          type="button"
          @click="emit('vote', winner.id, 0)"
          class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
          :class="{ 'ring-1 ring-slate-400 bg-slate-700': currentUser && winner.votes?.[currentUser.uid]?.score === 0 }"
          title="🤔 מתלבט (0)"
        >
          🤔
        </button>
        <button
          type="button"
          @click="emit('vote', winner.id, -1)"
          class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
          :class="{ 'ring-1 ring-rose-400 bg-rose-500/20': currentUser && winner.votes?.[currentUser.uid]?.score === -1 }"
          title="👎 פחות מתאים (-1)"
        >
          👎
        </button>
        <span class="text-[10px] text-slate-400 font-mono pr-1">({{ countVotes(winner.votes) }})</span>
      </div>
    </template>

    <!-- ======================================================== -->
    <!-- CASE B: UNDECIDED - Miniature Frame Inside Single Card   -->
    <!-- ======================================================== -->
    <template v-else>
      <div
        class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 border border-purple-500/30 cursor-pointer group/media p-0.5"
        @click="emit('open-decision', group)"
      >
        <!-- Empty state if no photos yet -->
        <div v-if="photos.length === 0" class="h-full flex flex-col items-center justify-center text-center p-2 text-slate-500 text-xs">
          <span>⚔️ אין תמונות בקבוצה</span>
          <span class="text-[10px] text-purple-400 underline mt-1">לחץ להוספת תמונות</span>
        </div>

        <!-- 1 Photo: Full single photo with hint -->
        <div v-else-if="photos.length === 1" class="relative h-full overflow-hidden rounded bg-slate-950">
          <img :src="photos[0].photo_data?.thumbnail" class="w-full h-full object-cover group-hover/media:scale-105 transition duration-300" />
        </div>

        <!-- 2 Photos: Side-by-side (50% / 50%) -->
        <div v-else-if="photos.length === 2" class="grid grid-cols-2 gap-1 h-full">
          <div v-for="p in photos" :key="p.id" class="relative h-full overflow-hidden rounded bg-slate-950">
            <img :src="p.photo_data?.thumbnail" class="w-full h-full object-cover group-hover/media:scale-105 transition duration-300" />
          </div>
        </div>

        <!-- 3 Photos: 1 on right, 2 stacked on left -->
        <div v-else-if="photos.length === 3" class="grid grid-cols-2 gap-1 h-full">
          <div class="h-full overflow-hidden rounded bg-slate-950">
            <img :src="photos[0].photo_data?.thumbnail" class="w-full h-full object-cover group-hover/media:scale-105 transition duration-300" />
          </div>
          <div class="grid grid-rows-2 gap-1 h-full">
            <div v-for="p in photos.slice(1, 3)" :key="p.id" class="h-full overflow-hidden rounded bg-slate-950">
              <img :src="p.photo_data?.thumbnail" class="w-full h-full object-cover group-hover/media:scale-105 transition duration-300" />
            </div>
          </div>
        </div>

        <!-- 4 or More Photos: 2x2 grid with +N on 4th -->
        <div v-else class="grid grid-cols-2 grid-rows-2 gap-1 h-full">
          <div
            v-for="(p, idx) in photos.slice(0, 4)"
            :key="p.id"
            class="relative h-full overflow-hidden rounded bg-slate-950"
          >
            <img :src="p.photo_data?.thumbnail" class="w-full h-full object-cover group-hover/media:scale-105 transition duration-300" />
            <div v-if="idx === 3 && photos.length > 4" class="absolute inset-0 bg-slate-950/80 flex items-center justify-center text-xs font-bold text-white">
              +{{ photos.length - 3 }}
            </div>
          </div>
        </div>

        <!-- Frosted Glass Bottom Overlay Pill -->
        <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950 via-slate-950/80 to-transparent p-2 flex items-center justify-between">
          <span class="text-[10px] text-purple-200 font-bold flex items-center gap-1">
            <span>⚔️</span>
            <span>{{ photos.length }} מתחרות</span>
          </span>
          <span class="px-2 py-0.5 bg-purple-600 hover:bg-purple-500 text-white rounded text-[10px] font-bold shadow flex items-center gap-0.5">
            <span>הכרע ובחר</span>
            <span>👑</span>
          </span>
        </div>
      </div>

      <!-- Undecided Subtitle / Hint -->
      <div class="flex items-center justify-between text-[11px] text-slate-400">
        <span class="truncate">הכרעה פתוחה ({{ photos.length }} חלופות)</span>
        <button
          type="button"
          @click.stop="emit('open-decision', group)"
          class="text-purple-300 hover:underline cursor-pointer shrink-0"
        >
          פתח השוואה ⬅
        </button>
      </div>
    </template>

    <!-- Gemini AI Head-to-Head Comparison Button -->
    <button
      type="button"
      @click.stop="emit('compare-ai', group)"
      class="w-full py-1 px-2 rounded-lg bg-purple-950/40 hover:bg-purple-900/60 text-purple-300 border border-purple-500/30 text-[11px] font-medium flex items-center justify-center gap-1.5 transition cursor-pointer"
    >
      <span>✨</span>
      <span>השוואת AI מי עדיפה</span>
      <span v-if="group.ai_comparison" class="text-[10px] text-emerald-400">✓ מוכן</span>
    </button>

    <!-- Column Movement Actions (Owner only) -->
    <div v-if="isOwner" class="pt-1 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-900">
      <!-- Sure Column Actions -->
      <template v-if="column === 'sure'">
        <button
          type="button"
          @click="emit('toggle-area', { groupId: group.id, currentArea: group.area || 'exhibition' })"
          class="text-indigo-300 hover:underline cursor-pointer"
        >
          {{ (group.area || 'exhibition') === 'wall' ? 'לתערוכה 🖼️' : 'לקיר 🧱' }}
        </button>
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'maybe' })"
          class="hover:text-purple-300 cursor-pointer"
        >
          לאפשרית ⬅
        </button>
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'pool' })"
          class="hover:text-slate-200 cursor-pointer"
        >
          למאגר ➡
        </button>
      </template>

      <!-- Maybe Column Actions -->
      <template v-else-if="column === 'maybe'">
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'sure' })"
          class="text-amber-300 hover:underline cursor-pointer font-semibold"
        >
          🌟 קדם לבטוחה
        </button>
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'pool' })"
          class="hover:text-slate-200 cursor-pointer"
        >
          למאגר ➡
        </button>
      </template>

      <!-- Pool Column Actions -->
      <template v-else-if="column === 'pool'">
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'sure' })"
          class="text-amber-300 hover:underline cursor-pointer font-semibold"
        >
          🌟 בטוחה ⬅
        </button>
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'maybe' })"
          class="text-sky-300 hover:underline cursor-pointer font-semibold"
        >
          🤔 אפשרית ⬅
        </button>
      </template>

      <!-- Rejected Column Actions -->
      <template v-else>
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'maybe' })"
          class="text-sky-300 hover:underline cursor-pointer"
        >
          ↩ החזר לאפשרית
        </button>
        <button
          type="button"
          @click="emit('move-status', { groupId: group.id, newStatus: 'sure' })"
          class="text-amber-300 hover:underline cursor-pointer"
        >
          🌟 בטוחה
        </button>
      </template>
    </div>
  </div>
</template>
