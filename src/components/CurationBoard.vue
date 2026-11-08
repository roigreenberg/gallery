<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import {
  auth,
  subscribeToAuth,
  loginWithGoogle,
  logoutUser,
  isUserOwner
} from '../utils/firebase.js';
import {
  subscribeToCurationItems,
  subscribeToSubGroups,
  addPhotoToCuration,
  batchAddPhotosToCuration,
  updateCurationStatus,
  voteOnCurationItem,
  removeVoteOnCurationItem,
  saveGeminiCritique,
  removeCurationItem,
  createSubGroup,
  updateSubGroup,
  deleteSubGroup
} from '../utils/curationService.js';
import {
  getGeminiApiKey,
  saveGeminiApiKey,
  requestPhotoCritique,
  requestGroupComparison
} from '../utils/geminiCurator.js';

const props = defineProps({
  initialPhotos: {
    type: Array,
    required: true
  }
});

// Auth & Permissions
const currentUser = ref(null);
const isOwner = ref(false);
const isAuthLoading = ref(true);
let unsubAuth = null;

// Curation Data
const curationItems = ref([]);
const subGroups = ref([]);
let unsubItems = null;
let unsubGroups = null;

// UI States
const activeArea = ref('exhibition'); // 'exhibition' | 'wall' | 'all'
const activeTab = ref('board'); // 'board' | 'groups' | 'pool'
const searchQuery = ref('');
const sortBy = ref('score_desc'); // 'score_desc' | 'votes_desc' | 'newest' | 'species'

// Modals
const showImportModal = ref(false);
const importSearch = ref('');
const importSelected = ref(new Set());
const importTargetArea = ref('exhibition');
const isImporting = ref(false);

// Sub-group Creation Modal
const showCreateGroupModal = ref(false);
const newGroupName = ref('');
const newGroupArea = ref('exhibition');

// Gemini AI State
const geminiApiKey = ref('');
const showApiKeyModal = ref(false);
const tempApiKey = ref('');
const isAnalyzing = ref(false);
const activeCritiquePhoto = ref(null);
const activeCritiqueText = ref('');
const activeComparisonGroup = ref(null);
const activeComparisonText = ref('');

// Lightbox preview inside curation
const previewPhoto = ref(null);

const homeUrl = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/`;

onMounted(() => {
  unsubAuth = subscribeToAuth(async (user) => {
    currentUser.value = user;
    isOwner.value = isUserOwner(user);
    isAuthLoading.value = false;

    if (user) {
      const key = await getGeminiApiKey(user);
      geminiApiKey.value = key;
    }
  });

  unsubItems = subscribeToCurationItems((items) => {
    curationItems.value = items;
  });

  unsubGroups = subscribeToSubGroups((groups) => {
    subGroups.value = groups;
  });
});

onUnmounted(() => {
  if (unsubAuth) unsubAuth();
  if (unsubItems) unsubItems();
  if (unsubGroups) unsubGroups();
});

// Computed photo stats & calculations
const calculateScore = (votes = {}) => {
  let score = 0;
  for (const uid in votes) {
    score += (votes[uid]?.score || 0);
  }
  return score;
};

const countVotes = (votes = {}) => {
  return Object.keys(votes).length;
};

// Automatically derive exhibition items from initialPhotos (196 exhibition candidates)
const defaultExhibitionItems = computed(() => {
  return (props.initialPhotos || [])
    .filter(p => p.is_exhibition_candidate || p.exhibition?.candidate)
    .map(p => {
      const score = p.exhibition_score || p.exhibition?.score || 1;
      const status = score === 2 ? 'sure' : 'maybe';
      return {
        id: p.id,
        photo_id: p.id,
        photo_data: {
          id: p.id,
          title: p.title || p.ai?.title || p.filename || '',
          title_en: p.title_en || p.ai?.title_en || '',
          thumbnail: p.thumb_url || p.paths?.thumbnail || p.thumbnail || '',
          display: p.display_url || p.paths?.display || p.display || '',
          species_he: p.species_he || p.ai?.species_hebrew || '',
          species_en: p.species_en || p.ai?.species_en || '',
          species_la: p.species_la || p.ai?.species_latin || '',
          category: p.category || p.ai?.category || 'wildlife',
          humorous_description: p.humorous_description || p.ai?.humorous_description || '',
          humorous_description_en: p.humorous_description_en || p.ai?.humorous_description_en || '',
          exhibition_score: score,
          exif: p.exif || {}
        },
        area: 'exhibition',
        status: status,
        group_id: null,
        group_name: null,
        votes: {},
        ai_critique: null,
        notes: '',
        is_default: true
      };
    });
});

// Merged items: default exhibition candidates + any custom overrides/votes from Firestore
const effectiveCurationItems = computed(() => {
  const map = new Map();
  for (const item of defaultExhibitionItems.value) {
    map.set(item.id, item);
  }

  for (const fireItem of curationItems.value) {
    const key = fireItem.photo_id || fireItem.id;
    if (map.has(key)) {
      const def = map.get(key);
      map.set(key, {
        ...def,
        ...fireItem,
        photo_data: { ...def.photo_data, ...(fireItem.photo_data || {}) }
      });
    } else {
      map.set(key, fireItem);
    }
  }

  return Array.from(map.values());
});

// Filtered items based on area & search
const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  return effectiveCurationItems.value.filter(item => {
    if (activeArea.value !== 'all' && item.area !== activeArea.value) {
      return false;
    }
    if (q) {
      const title = (item.photo_data?.title || '').toLowerCase();
      const species = (item.photo_data?.species_he || item.photo_data?.species_en || '').toLowerCase();
      if (!title.includes(q) && !species.includes(q)) return false;
    }
    return true;
  });
});

// Tiers breakdown
const sureItems = computed(() => filteredItems.value.filter(i => i.status === 'sure'));
const maybeItems = computed(() => filteredItems.value.filter(i => i.status === 'maybe'));
const groupItems = computed(() => filteredItems.value.filter(i => i.status === 'group'));
const poolItems = computed(() => filteredItems.value.filter(i => i.status === 'pool' || !i.status));
const rejectedItems = computed(() => filteredItems.value.filter(i => i.status === 'rejected'));

// Sub-groups for active area
const activeSubGroups = computed(() => {
  return subGroups.value.filter(g => activeArea.value === 'all' || g.area === activeArea.value);
});

const getGroupPhotos = (groupId) => {
  return effectiveCurationItems.value.filter(i => i.group_id === groupId);
};

// Voting Actions
const handleVote = async (photoId, score) => {
  if (!currentUser.value) {
    try {
      await loginWithGoogle();
    } catch (e) {}
    return;
  }
  const item = effectiveCurationItems.value.find(i => i.photo_id === photoId || i.id === photoId);
  if (!item) return;
  const currentVote = item?.votes?.[currentUser.value.uid]?.score;

  try {
    if (currentVote === score) {
      await removeVoteOnCurationItem(photoId, currentUser.value);
    } else {
      await voteOnCurationItem(photoId, currentUser.value, score, item.photo_data);
    }
  } catch (err) {
    console.error('Vote error:', err);
  }
};

// Moving between tiers
const handleMoveStatus = async (photoId, newStatus, newArea = null) => {
  if (!isOwner.value) {
    if (!currentUser.value) {
      try { await loginWithGoogle(); } catch (e) {}
    }
    return;
  }
  const item = effectiveCurationItems.value.find(i => i.photo_id === photoId || i.id === photoId);
  try {
    const updates = { status: newStatus };
    if (newArea) updates.area = newArea;
    if (newStatus !== 'group') {
      updates.groupId = null;
      updates.groupName = null;
    }
    await updateCurationStatus(photoId, updates, item?.photo_data);
  } catch (err) {
    console.error('Status update error:', err);
  }
};

// Assign to sub-group
const handleAssignToGroup = async (photoId, groupId, groupName) => {
  try {
    await updateCurationStatus(photoId, {
      status: 'group',
      groupId,
      groupName
    });
  } catch (err) {
    console.error('Assign group error:', err);
  }
};

// Pick sub-group winner
const handleSelectGroupWinner = async (group, winnerPhoto) => {
  if (!isOwner.value) return;
  try {
    await updateSubGroup(group.id, { winner_id: winnerPhoto.id });
    // Move winner to 'sure'
    await updateCurationStatus(winnerPhoto.id, {
      status: 'sure',
      groupId: group.id,
      groupName: group.name
    });
  } catch (err) {
    console.error('Pick winner error:', err);
  }
};

// Drag & Drop
const draggedPhotoId = ref(null);

const handleDragStart = (e, photoId) => {
  draggedPhotoId.value = photoId;
  e.dataTransfer.effectAllowed = 'move';
};

const handleDrop = async (newStatus) => {
  if (!draggedPhotoId.value || !isOwner.value) return;
  await handleMoveStatus(draggedPhotoId.value, newStatus);
  draggedPhotoId.value = null;
};

// Sub-group Creation
const handleCreateGroup = async () => {
  const name = newGroupName.value.trim();
  if (!name) return;
  try {
    await createSubGroup(name, newGroupArea.value);
    newGroupName.value = '';
    showCreateGroupModal.value = false;
  } catch (err) {
    console.error('Create group error:', err);
  }
};

// Gemini AI Critique
const handleRequestCritique = async (item) => {
  if (!geminiApiKey.value) {
    showApiKeyModal.value = true;
    return;
  }

  isAnalyzing.value = true;
  activeCritiquePhoto.value = item;
  activeCritiqueText.value = '';

  try {
    const text = await requestPhotoCritique(item.photo_data, geminiApiKey.value);
    activeCritiqueText.value = text;
    await saveGeminiCritique(item.photo_id || item.id, text);
  } catch (err) {
    activeCritiqueText.value = `שגיאה בקבלת ניתוח: ${err.message}`;
  } finally {
    isAnalyzing.value = false;
  }
};

// Gemini Head-to-Head Comparison
const handleCompareGroup = async (group) => {
  if (!geminiApiKey.value) {
    showApiKeyModal.value = true;
    return;
  }

  const photos = getGroupPhotos(group.id);
  if (photos.length < 2) {
    alert('יש להוסיף לפחות 2 תמונות לתת-הקבוצה לפני שניתן להשוות.');
    return;
  }

  isAnalyzing.value = true;
  activeComparisonGroup.value = group;
  activeComparisonText.value = '';

  try {
    const text = await requestGroupComparison(group.name, photos, geminiApiKey.value);
    activeComparisonText.value = text;
    await updateSubGroup(group.id, { ai_comparison: text });
  } catch (err) {
    activeComparisonText.value = `שגיאה בהשוואה: ${err.message}`;
  } finally {
    isAnalyzing.value = false;
  }
};

// Gemini API Key Save
const handleSaveApiKey = async () => {
  if (!tempApiKey.value.trim()) return;
  await saveGeminiApiKey(tempApiKey.value, currentUser.value);
  geminiApiKey.value = tempApiKey.value.trim();
  showApiKeyModal.value = false;
};

// Gallery Import Search & Selection
const importAvailablePhotos = computed(() => {
  const existingIds = new Set(curationItems.value.map(i => i.photo_id || i.id));
  const q = importSearch.value.trim().toLowerCase();

  return props.initialPhotos
    .filter(p => !existingIds.has(p.id))
    .filter(p => {
      if (!q) return true;
      const title = (p.title || p.ai?.title || '').toLowerCase();
      const spHe = (p.ai?.species_hebrew || '').toLowerCase();
      const spEn = (p.ai?.species_en || '').toLowerCase();
      const tags = (p.ai?.tags || []).join(' ').toLowerCase();
      return title.includes(q) || spHe.includes(q) || spEn.includes(q) || tags.includes(q);
    })
    .slice(0, 48);
});

const toggleImportItem = (photo) => {
  if (importSelected.value.has(photo.id)) {
    importSelected.value.delete(photo.id);
  } else {
    importSelected.value.add(photo.id);
  }
  // Trigger reactivity
  importSelected.value = new Set(importSelected.value);
};

const handleExecuteImport = async () => {
  if (importSelected.value.size === 0) return;
  isImporting.value = true;

  try {
    const selectedPhotosList = props.initialPhotos.filter(p => importSelected.value.has(p.id));
    await batchAddPhotosToCuration(selectedPhotosList, importTargetArea.value, 'pool');
    importSelected.value.clear();
    showImportModal.value = false;
  } catch (err) {
    console.error('Import error:', err);
  } finally {
    isImporting.value = false;
  }
};
</script>

<template>
  <div class="min-h-screen bg-[#07090e] text-slate-100 selection:bg-indigo-500 selection:text-white" dir="rtl">
    
    <!-- Loading State -->
    <div v-if="isAuthLoading" class="min-h-[70vh] flex flex-col items-center justify-center space-y-4">
      <div class="w-10 h-10 rounded-full border-3 border-indigo-500 border-t-transparent animate-spin"></div>
      <p class="text-sm text-slate-400">טוען נתונים...</p>
    </div>

    <!-- Main Curation Workspace (Accessible to everyone, sign-in enables voting & curating) -->
    <div v-else class="max-w-[1700px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      
      <!-- Top Bar: Header & Controls -->
      <header class="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 sm:p-5 backdrop-blur-xl flex flex-wrap items-center justify-between gap-4">
        <!-- Brand & Context -->
        <div class="flex items-center gap-3.5">
          <a
            :href="homeUrl"
            class="w-10 h-10 rounded-xl bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-300 hover:text-white transition cursor-pointer text-sm font-semibold"
            title="חזרה לגלריה הראשית"
          >
            ←
          </a>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-xl sm:text-2xl font-black text-white tracking-tight">מועמדות לתערוכה וקיר תמונות</h1>
              <span v-if="isOwner" class="px-2 py-0.5 text-[11px] bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-full font-bold">
                👑 בעלים ואוצר ראשי
              </span>
              <span v-else-if="currentUser" class="px-2 py-0.5 text-[11px] bg-sky-500/20 text-sky-300 border border-sky-500/30 rounded-full font-semibold">
                🗳️ שופט / מדרג
              </span>
              <span v-else class="px-2 py-0.5 text-[11px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 rounded-full font-semibold">
                🏛️ תצוגת מועמדות
              </span>
            </div>
            <p v-if="currentUser" class="text-xs text-slate-400 mt-0.5">
              שלום <strong class="text-slate-200">{{ currentUser.displayName || currentUser.email }}</strong> • דרג תמונות, הוסף הערות ובחר מועמדות.
            </p>
            <p v-else class="text-xs text-slate-400 mt-0.5">
              צפייה במועמדות לתערוכה ולקיר התמונות. התחבר עם חשבון Google כדי להצביע ולהשפיע.
            </p>
          </div>
        </div>

        <!-- Area Switcher (Exhibition vs Photo Wall vs All) -->
        <div class="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800">
          <button
            type="button"
            @click="activeArea = 'exhibition'"
            class="px-4 py-2 rounded-lg text-xs sm:text-sm font-semibold transition cursor-pointer flex items-center gap-2"
            :class="activeArea === 'exhibition' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>🖼️</span>
            <span>תערוכה ראשית</span>
            <span class="px-1.5 py-0.2 bg-black/30 rounded-full text-[11px]">
              {{ effectiveCurationItems.filter(i => i.area === 'exhibition' && i.status === 'sure').length }}
            </span>
          </button>

          <button
            type="button"
            @click="activeArea = 'wall'"
            class="px-4 py-2 rounded-lg text-xs sm:text-sm font-semibold transition cursor-pointer flex items-center gap-2"
            :class="activeArea === 'wall' ? 'bg-emerald-600 text-white shadow-lg' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>🧱</span>
            <span>קיר תמונות</span>
            <span class="px-1.5 py-0.2 bg-black/30 rounded-full text-[11px]">
              {{ effectiveCurationItems.filter(i => i.area === 'wall' && i.status === 'sure').length }}
            </span>
          </button>

          <button
            type="button"
            @click="activeArea = 'all'"
            class="px-3.5 py-2 rounded-lg text-xs font-medium transition cursor-pointer"
            :class="activeArea === 'all' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>הכל ({{ effectiveCurationItems.length }})</span>
          </button>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center gap-2">
          <!-- Sign in button if not logged in -->
          <button
            v-if="!currentUser"
            type="button"
            @click="loginWithGoogle"
            class="px-3.5 py-2 rounded-xl bg-white hover:bg-slate-100 text-slate-900 text-xs font-bold transition shadow-sm flex items-center gap-2 cursor-pointer"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
            <span>התחבר להצבעה</span>
          </button>

          <!-- Import Photos (Owner only) -->
          <button
            v-if="isOwner"
            type="button"
            @click="showImportModal = true"
            class="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold transition shadow-sm flex items-center gap-1.5 cursor-pointer"
          >
            <span>➕</span>
            <span>ייבא תמונות נוספות</span>
          </button>

          <!-- Create Sub-Group (Owner only) -->
          <button
            v-if="isOwner"
            type="button"
            @click="showCreateGroupModal = true"
            class="px-3.5 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition shadow-sm flex items-center gap-1.5 cursor-pointer"
          >
            <span>⚔️</span>
            <span>תת-קבוצה (ראש בראש)</span>
          </button>

          <!-- Gemini Key Config -->
          <button
            type="button"
            @click="showApiKeyModal = true"
            class="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-indigo-300 text-xs font-medium border border-indigo-500/30 transition flex items-center gap-1.5 cursor-pointer"
            title="הגדרות Gemini AI"
          >
            <span>🤖</span>
            <span class="hidden sm:inline">אוצר AI</span>
          </button>
        </div>
      </header>

      <!-- View Navigation Tabs: Board Columns vs Sub-Groups ("Head to Head") vs Pool -->
      <div class="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="activeTab = 'board'"
            class="px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer flex items-center gap-2"
            :class="activeTab === 'board' ? 'bg-slate-800 text-white border border-slate-700' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>📋</span>
            <span>לוח מועמדויות (Kanban)</span>
          </button>

          <button
            type="button"
            @click="activeTab = 'groups'"
            class="px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer flex items-center gap-2"
            :class="activeTab === 'groups' ? 'bg-slate-800 text-white border border-slate-700' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>⚔️</span>
            <span>זירת השוואות ראש בראש ({{ activeSubGroups.length }})</span>
          </button>

          <button
            type="button"
            @click="activeTab = 'pool'"
            class="px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer flex items-center gap-2"
            :class="activeTab === 'pool' ? 'bg-slate-800 text-white border border-slate-700' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>📥</span>
            <span>כל המאגר הממתין ({{ poolItems.length }})</span>
          </button>
        </div>

        <!-- Quick Search Filter -->
        <div class="w-64">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="סנן לפי שם חיה או כותרת..."
            class="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
          />
        </div>
      </div>

      <!-- ======================================================== -->
      <!-- TAB 1: KANBAN BOARD VIEW                                 -->
      <!-- ======================================================== -->
      <div v-if="activeTab === 'board'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        
        <!-- Column 1: 🌟 מועמדות בטוחות (Sure) -->
        <div
          class="bg-slate-900/60 border border-amber-500/30 rounded-2xl p-4 flex flex-col space-y-3 backdrop-blur-md"
          @dragover.prevent
          @drop="handleDrop('sure')"
        >
          <div class="flex items-center justify-between pb-2 border-b border-amber-500/20">
            <div class="flex items-center gap-2">
              <span class="text-base">🌟</span>
              <h3 class="font-bold text-amber-300 text-sm">מועמדות בטוחות</h3>
            </div>
            <span class="px-2 py-0.5 bg-amber-950/80 text-amber-300 border border-amber-500/40 rounded-full text-xs font-bold font-mono">
              {{ sureItems.length }}
            </span>
          </div>

          <div class="space-y-3 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <div
              v-for="item in sureItems"
              :key="item.id"
              :draggable="isOwner"
              @dragstart="handleDragStart($event, item.id)"
              class="group bg-slate-950 border border-slate-800 hover:border-amber-500/50 rounded-xl p-3 space-y-2.5 transition shadow-lg relative"
            >
              <!-- Image Preview -->
              <div
                class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer"
                @click="previewPhoto = item.photo_data"
              >
                <img :src="item.photo_data?.thumbnail || item.photo_data?.display" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
                <span class="absolute top-2 right-2 px-2 py-0.5 bg-slate-950/80 backdrop-blur-md rounded-full text-[10px] text-amber-300 border border-amber-500/40 font-bold">
                  {{ item.photo_data?.species_he || 'תמונה' }}
                </span>
                <!-- Net Score Badge -->
                <span
                  class="absolute bottom-2 left-2 px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1 shadow-md"
                  :class="calculateScore(item.votes) > 0 ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-500/40' : (calculateScore(item.votes) < 0 ? 'bg-rose-950/90 text-rose-300 border border-rose-500/40' : 'bg-slate-900 text-slate-300 border border-slate-700')"
                >
                  <span>ציון:</span>
                  <span class="font-mono">{{ calculateScore(item.votes) }}</span>
                </span>
              </div>

              <!-- Title & EXIF -->
              <div>
                <h4 class="text-xs font-bold text-slate-100 truncate">{{ item.photo_data?.title }}</h4>
                <p class="text-[10px] text-slate-400 truncate">
                  {{ item.photo_data?.exif?.camera_model }} • {{ item.photo_data?.exif?.lens_model }}
                </p>
              </div>

              <!-- Voting Bar (4 options) -->
              <div class="flex items-center justify-between bg-slate-900/80 p-1.5 rounded-lg border border-slate-800 text-xs">
                <button
                  type="button"
                  @click="handleVote(item.id, 2)"
                  class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
                  :class="{ 'ring-1 ring-amber-400 bg-amber-500/20': currentUser && item.votes?.[currentUser.uid]?.score === 2 }"
                  title="🔥 חובה בתערוכה (+2)"
                >
                  🔥
                </button>
                <button
                  type="button"
                  @click="handleVote(item.id, 1)"
                  class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
                  :class="{ 'ring-1 ring-emerald-400 bg-emerald-500/20': currentUser && item.votes?.[currentUser.uid]?.score === 1 }"
                  title="👍 מוצלחת מאוד (+1)"
                >
                  👍
                </button>
                <button
                  type="button"
                  @click="handleVote(item.id, 0)"
                  class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
                  :class="{ 'ring-1 ring-slate-400 bg-slate-700': currentUser && item.votes?.[currentUser.uid]?.score === 0 }"
                  title="🤔 מתלבט (0)"
                >
                  🤔
                </button>
                <button
                  type="button"
                  @click="handleVote(item.id, -1)"
                  class="p-1 rounded hover:bg-slate-800 transition cursor-pointer"
                  :class="{ 'ring-1 ring-rose-400 bg-rose-500/20': currentUser && item.votes?.[currentUser.uid]?.score === -1 }"
                  title="👎 פחות מתאים (-1)"
                >
                  👎
                </button>
                <span class="text-[10px] text-slate-400 font-mono pr-1">({{ countVotes(item.votes) }})</span>
              </div>

              <!-- Gemini Consultation Button -->
              <button
                type="button"
                @click="handleRequestCritique(item)"
                class="w-full py-1 px-2 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/80 text-indigo-300 border border-indigo-600/40 text-[11px] font-medium flex items-center justify-center gap-1.5 transition cursor-pointer"
              >
                <span>✨</span>
                <span>חוות דעת ג'ימיני</span>
                <span v-if="item.ai_critique" class="text-[10px] text-emerald-400">✓ מוכן</span>
              </button>

              <!-- Owner Quick Actions -->
              <div v-if="isOwner" class="pt-1 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-900">
                <button
                  type="button"
                  @click="handleMoveStatus(item.id, 'maybe')"
                  class="hover:text-amber-300 cursor-pointer"
                >
                  העבר לאפשרית ⬅
                </button>
                <button
                  type="button"
                  @click="handleMoveStatus(item.id, 'rejected')"
                  class="hover:text-rose-400 cursor-pointer"
                >
                  פסול ✕
                </button>
              </div>
            </div>

            <div v-if="sureItems.length === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
              גרור לכאן תמונות בטוחות לתערוכה
            </div>
          </div>
        </div>

        <!-- Column 2: 🤔 מועמדות אפשריות (Maybe / Shortlist) -->
        <div
          class="bg-slate-900/60 border border-sky-500/30 rounded-2xl p-4 flex flex-col space-y-3 backdrop-blur-md"
          @dragover.prevent
          @drop="handleDrop('maybe')"
        >
          <div class="flex items-center justify-between pb-2 border-b border-sky-500/20">
            <div class="flex items-center gap-2">
              <span class="text-base">🤔</span>
              <h3 class="font-bold text-sky-300 text-sm">מועמדות אפשריות</h3>
            </div>
            <span class="px-2 py-0.5 bg-sky-950/80 text-sky-300 border border-sky-500/40 rounded-full text-xs font-bold font-mono">
              {{ maybeItems.length }}
            </span>
          </div>

          <div class="space-y-3 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <div
              v-for="item in maybeItems"
              :key="item.id"
              :draggable="isOwner"
              @dragstart="handleDragStart($event, item.id)"
              class="group bg-slate-950 border border-slate-800 hover:border-sky-500/50 rounded-xl p-3 space-y-2.5 transition shadow-lg"
            >
              <div
                class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer"
                @click="previewPhoto = item.photo_data"
              >
                <img :src="item.photo_data?.thumbnail || item.photo_data?.display" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
                <span class="absolute top-2 right-2 px-2 py-0.5 bg-slate-950/80 backdrop-blur-md rounded-full text-[10px] text-sky-300 border border-sky-500/40 font-bold">
                  {{ item.photo_data?.species_he || 'תמונה' }}
                </span>
                <span
                  class="absolute bottom-2 left-2 px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1 shadow-md"
                  :class="calculateScore(item.votes) > 0 ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-500/40' : (calculateScore(item.votes) < 0 ? 'bg-rose-950/90 text-rose-300 border border-rose-500/40' : 'bg-slate-900 text-slate-300 border border-slate-700')"
                >
                  <span class="font-mono">{{ calculateScore(item.votes) }}</span>
                </span>
              </div>

              <div>
                <h4 class="text-xs font-bold text-slate-100 truncate">{{ item.photo_data?.title }}</h4>
                <p class="text-[10px] text-slate-400 truncate">{{ item.photo_data?.exif?.camera_model }}</p>
              </div>

              <!-- Voting Bar -->
              <div class="flex items-center justify-between bg-slate-900/80 p-1.5 rounded-lg border border-slate-800 text-xs">
                <button @click="handleVote(item.id, 2)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-amber-400 bg-amber-500/20': currentUser && item.votes?.[currentUser.uid]?.score === 2 }" title="🔥 חובה (+2)">🔥</button>
                <button @click="handleVote(item.id, 1)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-emerald-400 bg-emerald-500/20': currentUser && item.votes?.[currentUser.uid]?.score === 1 }" title="👍 מוצלחת (+1)">👍</button>
                <button @click="handleVote(item.id, 0)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-slate-400 bg-slate-700': currentUser && item.votes?.[currentUser.uid]?.score === 0 }" title="🤔 מתלבט (0)">🤔</button>
                <button @click="handleVote(item.id, -1)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-rose-400 bg-rose-500/20': currentUser && item.votes?.[currentUser.uid]?.score === -1 }" title="👎 פחות מתאים (-1)">👎</button>
                <span class="text-[10px] text-slate-400 font-mono pr-1">({{ countVotes(item.votes) }})</span>
              </div>

              <button
                type="button"
                @click="handleRequestCritique(item)"
                class="w-full py-1 px-2 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/80 text-indigo-300 border border-indigo-600/40 text-[11px] font-medium flex items-center justify-center gap-1.5 transition cursor-pointer"
              >
                <span>✨</span>
                <span>חוות דעת ג'ימיני</span>
                <span v-if="item.ai_critique" class="text-[10px] text-emerald-400">✓ מוכן</span>
              </button>

              <div v-if="isOwner" class="pt-1 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-900">
                <button type="button" @click="handleMoveStatus(item.id, 'sure')" class="text-amber-300 hover:underline cursor-pointer">
                  🌟 קדם לבטוחה
                </button>
                <button type="button" @click="handleMoveStatus(item.id, 'rejected')" class="hover:text-rose-400 cursor-pointer">
                  פסול ✕
                </button>
              </div>
            </div>

            <div v-if="maybeItems.length === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
              אין מועמדות מתלבטות כרגע
            </div>
          </div>
        </div>

        <!-- Column 3: ⚔️ מועמדות מבין כמה – תתי-קבוצות (Group / Head-to-Head) -->
        <div class="bg-slate-900/60 border border-purple-500/30 rounded-2xl p-4 flex flex-col space-y-3 backdrop-blur-md">
          <div class="flex items-center justify-between pb-2 border-b border-purple-500/20">
            <div class="flex items-center gap-2">
              <span class="text-base">⚔️</span>
              <h3 class="font-bold text-purple-300 text-sm">מועמדות מבין כמה</h3>
            </div>
            <span class="px-2 py-0.5 bg-purple-950/80 text-purple-300 border border-purple-500/40 rounded-full text-xs font-bold font-mono">
              {{ groupItems.length }}
            </span>
          </div>

          <p class="text-[11px] text-slate-400">
            תמונות דומות שמתחרות ראש בראש. לחץ על כרטיסיית "זירת השוואות" כדי להכריע ביניהן.
          </p>

          <div class="space-y-3 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <div
              v-for="item in groupItems"
              :key="item.id"
              class="bg-slate-950 border border-purple-500/40 rounded-xl p-3 space-y-2 shadow-lg"
            >
              <div class="flex items-center gap-3">
                <img :src="item.photo_data?.thumbnail" class="w-14 h-14 rounded-lg object-cover cursor-pointer shrink-0" @click="previewPhoto = item.photo_data" />
                <div class="flex-1 min-w-0">
                  <span class="inline-block px-1.5 py-0.2 bg-purple-900/60 text-purple-300 rounded text-[10px] font-bold truncate max-w-full">
                    קבוצה: {{ item.group_name || 'כללי' }}
                  </span>
                  <h4 class="text-xs font-bold text-slate-100 truncate mt-0.5">{{ item.photo_data?.title }}</h4>
                  <p class="text-[10px] text-slate-400">{{ item.photo_data?.species_he }}</p>
                </div>
              </div>

              <div v-if="isOwner" class="flex items-center justify-between pt-1 border-t border-slate-900 text-[10px]">
                <button type="button" @click="handleMoveStatus(item.id, 'sure')" class="text-amber-300 hover:underline cursor-pointer">
                  🏆 בחר כמנצחת
                </button>
                <button type="button" @click="handleMoveStatus(item.id, 'maybe')" class="text-slate-400 hover:underline cursor-pointer">
                  החזר לאפשרית
                </button>
              </div>
            </div>

            <div v-if="groupItems.length === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
              טרם שויכו תמונות לתתי-קבוצות
            </div>
          </div>
        </div>

        <!-- Column 4: ❌ נפסלו (Rejected) -->
        <div
          class="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 flex flex-col space-y-3 backdrop-blur-md opacity-85 hover:opacity-100 transition"
          @dragover.prevent
          @drop="handleDrop('rejected')"
        >
          <div class="flex items-center justify-between pb-2 border-b border-slate-800">
            <div class="flex items-center gap-2">
              <span class="text-base">❌</span>
              <h3 class="font-bold text-slate-400 text-sm">נפסלו / בארכיון</h3>
            </div>
            <span class="px-2 py-0.5 bg-slate-950 text-slate-400 border border-slate-800 rounded-full text-xs font-mono">
              {{ rejectedItems.length }}
            </span>
          </div>

          <div class="space-y-2.5 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <div
              v-for="item in rejectedItems"
              :key="item.id"
              class="flex items-center gap-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-2"
            >
              <img :src="item.photo_data?.thumbnail" class="w-12 h-12 rounded-lg object-cover cursor-pointer shrink-0 filter grayscale hover:grayscale-0 transition" @click="previewPhoto = item.photo_data" />
              <div class="flex-1 min-w-0">
                <h4 class="text-xs text-slate-300 truncate">{{ item.photo_data?.title }}</h4>
                <p class="text-[10px] text-slate-500 truncate">{{ item.photo_data?.species_he }}</p>
              </div>
              <button
                v-if="isOwner"
                type="button"
                @click="handleMoveStatus(item.id, 'maybe')"
                class="text-xs text-sky-400 hover:text-white px-2 py-1 bg-slate-800 rounded cursor-pointer shrink-0"
                title="החזר לרשימה"
              >
                ↩
              </button>
            </div>

            <div v-if="rejectedItems.length === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
              אין תמונות שנפסלו
            </div>
          </div>
        </div>

      </div>

      <!-- ======================================================== -->
      <!-- TAB 2: SUB-GROUPS ("זירת השוואות ראש בראש")              -->
      <!-- ======================================================== -->
      <div v-else-if="activeTab === 'groups'" class="space-y-6">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-bold text-white flex items-center gap-2">
              <span>⚔️</span>
              <span>זירת השוואות ראש בראש (תתי-קבוצות)</span>
            </h2>
            <p class="text-xs text-slate-400">
              כשיש לך כמה תמונות של אותו בעל חיים או זווית וצריך להכריע מי האחת שתעלה לתערוכה.
            </p>
          </div>
          <button
            v-if="isOwner"
            type="button"
            @click="showCreateGroupModal = true"
            class="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition cursor-pointer shadow-md"
          >
            + צור תת-קבוצה חדשה
          </button>
        </div>

        <div v-if="activeSubGroups.length === 0" class="text-center py-20 bg-slate-900/40 border border-dashed border-slate-800 rounded-3xl space-y-3">
          <span class="text-4xl block">⚔️</span>
          <h3 class="text-base font-bold text-slate-300">אין תתי-קבוצות פתוחות כרגע</h3>
          <p class="text-xs text-slate-500 max-w-sm mx-auto">
            צור קבוצה (למשל: "שלדג לבן-חזה - בחירת תנוחה") ושייך אליה 2-4 תמונות כדי להשוות ביניהן ולבקש את הכרעת ג'ימיני.
          </p>
        </div>

        <!-- Groups List -->
        <div v-else class="space-y-6">
          <div
            v-for="group in activeSubGroups"
            :key="group.id"
            class="bg-slate-900/80 border border-purple-500/30 rounded-2xl p-5 space-y-4 backdrop-blur-xl"
          >
            <!-- Group Header -->
            <div class="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800">
              <div class="flex items-center gap-2.5">
                <span class="text-xl">⚔️</span>
                <div>
                  <h3 class="font-bold text-base text-white">{{ group.name }}</h3>
                  <span class="text-xs text-purple-300 font-medium">
                    מסלול: {{ group.area === 'exhibition' ? 'תערוכה ראשית' : 'קיר תמונות' }} • {{ getGroupPhotos(group.id).length }} תמונות מתחרות
                  </span>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <!-- Gemini Compare Button -->
                <button
                  type="button"
                  @click="handleCompareGroup(group)"
                  class="px-3.5 py-1.5 rounded-xl bg-indigo-950 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-900/80 text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer"
                >
                  <span>✨</span>
                  <span>שאל את ג'ימיני מי המנצחת</span>
                </button>

                <button
                  v-if="isOwner"
                  type="button"
                  @click="deleteSubGroup(group.id)"
                  class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 transition cursor-pointer text-xs"
                  title="מחק קבוצה"
                >
                  🗑️
                </button>
              </div>
            </div>

            <!-- AI Comparison Verdict if exists -->
            <div v-if="group.ai_comparison" class="bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-4 text-xs text-indigo-100 leading-relaxed space-y-1">
              <div class="font-bold text-indigo-300 flex items-center gap-1.5">
                <span>🤖</span>
                <span>הכרעת האוצר הדיגיטלי (Gemini):</span>
              </div>
              <p class="whitespace-pre-wrap">{{ group.ai_comparison }}</p>
            </div>

            <!-- Competing Photos Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              <div
                v-for="photo in getGroupPhotos(group.id)"
                :key="photo.id"
                class="bg-slate-950 rounded-xl border p-3 space-y-2.5 transition relative"
                :class="group.winner_id === photo.id ? 'border-amber-400 ring-2 ring-amber-400/30 shadow-amber-500/20 shadow-lg' : 'border-slate-800 hover:border-slate-700'"
              >
                <!-- Winner Crown -->
                <div v-if="group.winner_id === photo.id" class="absolute -top-3 -right-2 z-10 px-2 py-0.5 bg-amber-500 text-slate-950 font-black rounded-full text-xs shadow-lg flex items-center gap-1">
                  <span>🏆 המנצחת שנבחרה!</span>
                </div>

                <div
                  class="aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer"
                  @click="previewPhoto = photo.photo_data"
                >
                  <img :src="photo.photo_data?.thumbnail || photo.photo_data?.display" class="w-full h-full object-cover hover:scale-105 transition" />
                </div>

                <div>
                  <h4 class="text-xs font-bold text-slate-100 truncate">{{ photo.photo_data?.title }}</h4>
                  <p class="text-[10px] text-slate-400">{{ photo.photo_data?.exif?.camera_model }} • {{ photo.photo_data?.exif?.aperture }}</p>
                </div>

                <!-- Score & Votes inside group -->
                <div class="flex items-center justify-between text-xs bg-slate-900 p-1.5 rounded-lg border border-slate-800">
                  <span class="text-slate-400 text-[10px]">דירוג:</span>
                  <div class="flex items-center gap-1">
                    <button @click="handleVote(photo.id, 2)" class="p-0.5 hover:scale-110 cursor-pointer">🔥</button>
                    <button @click="handleVote(photo.id, 1)" class="p-0.5 hover:scale-110 cursor-pointer">👍</button>
                    <button @click="handleVote(photo.id, -1)" class="p-0.5 hover:scale-110 cursor-pointer">👎</button>
                    <span class="font-mono font-bold text-amber-300 pr-1">{{ calculateScore(photo.votes) }}</span>
                  </div>
                </div>

                <!-- Pick as winner button (Owner only) -->
                <button
                  v-if="isOwner && group.winner_id !== photo.id"
                  type="button"
                  @click="handleSelectGroupWinner(group, photo)"
                  class="w-full py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500 text-amber-300 hover:text-slate-950 border border-amber-500/50 text-xs font-bold transition cursor-pointer flex items-center justify-center gap-1"
                >
                  <span>🏆</span>
                  <span>בחר כמנצחת</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ======================================================== -->
      <!-- TAB 3: POOL VIEW (ממתינות במאגר)                         -->
      <!-- ======================================================== -->
      <div v-else-if="activeTab === 'pool'" class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-bold text-white flex items-center gap-2">
              <span>📥</span>
              <span>מאגר תמונות ממתין להחלטה ({{ poolItems.length }})</span>
            </h2>
            <p class="text-xs text-slate-400">
              תמונות שהוצעו לתערוכה וטרם מוינו. בחר האם להעביר אותן לבטוחה, אפשרית, תת-קבוצה, או לפסול.
            </p>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div
            v-for="item in poolItems"
            :key="item.id"
            class="bg-slate-900 border border-slate-800 rounded-xl p-2.5 space-y-2 hover:border-slate-700 transition"
          >
            <div class="aspect-[3/2] rounded-lg overflow-hidden bg-slate-950 cursor-pointer" @click="previewPhoto = item.photo_data">
              <img :src="item.photo_data?.thumbnail" class="w-full h-full object-cover hover:scale-105 transition" />
            </div>

            <h4 class="text-xs font-bold text-slate-100 truncate">{{ item.photo_data?.title }}</h4>
            <p class="text-[10px] text-slate-400 truncate">{{ item.photo_data?.species_he }}</p>

            <!-- Quick Move Buttons -->
            <div v-if="isOwner" class="grid grid-cols-2 gap-1 pt-1 text-[10px]">
              <button
                type="button"
                @click="handleMoveStatus(item.id, 'sure')"
                class="py-1 bg-amber-500/20 text-amber-300 rounded hover:bg-amber-500 hover:text-black font-semibold cursor-pointer"
              >
                🌟 בטוחה
              </button>
              <button
                type="button"
                @click="handleMoveStatus(item.id, 'maybe')"
                class="py-1 bg-sky-500/20 text-sky-300 rounded hover:bg-sky-500 hover:text-black font-semibold cursor-pointer"
              >
                🤔 אפשרית
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- ======================================================== -->
    <!-- MODAL: IMPORT PHOTOS FROM EXISTING GALLERY               -->
    <!-- ======================================================== -->
    <div
      v-if="showImportModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
    >
      <div class="bg-slate-900 border border-slate-700 rounded-3xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden shadow-2xl">
        <header class="p-5 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 class="font-bold text-lg text-white">ייבוא תמונות מתוך הגלריה למאגר התערוכה</h3>
            <p class="text-xs text-slate-400">חפש וסמן תמונות להוספה. נבחרו: {{ importSelected.size }} תמונות.</p>
          </div>
          <button @click="showImportModal = false" class="text-slate-400 hover:text-white p-1 cursor-pointer">✕</button>
        </header>

        <div class="p-4 border-b border-slate-800 flex items-center gap-3">
          <input
            v-model="importSearch"
            type="text"
            placeholder="חפש לפי מין חיה, כותרת, תגית (לדוגמה: שלדג, שקיעה)..."
            class="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
          />
          <select
            v-model="importTargetArea"
            class="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200"
          >
            <option value="exhibition">יעד: תערוכה ראשית</option>
            <option value="wall">יעד: קיר תמונות</option>
          </select>
        </div>

        <div class="flex-1 overflow-y-auto p-4 grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
          <div
            v-for="photo in importAvailablePhotos"
            :key="photo.id"
            @click="toggleImportItem(photo)"
            class="group relative aspect-[3/2] rounded-xl overflow-hidden cursor-pointer border-2 transition"
            :class="importSelected.has(photo.id) ? 'border-sky-400 ring-2 ring-sky-400/40 scale-95' : 'border-slate-800 hover:border-slate-600'"
          >
            <img :src="photo.thumbnail || photo.display_url || photo.paths?.thumbnail" class="w-full h-full object-cover" />
            <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex flex-col justify-end p-2 text-right">
              <span class="text-[11px] font-bold text-white truncate">{{ photo.title || photo.ai?.title }}</span>
            </div>
            <span
              v-if="importSelected.has(photo.id)"
              class="absolute top-1.5 right-1.5 w-5 h-5 bg-sky-500 text-slate-950 font-black rounded-full flex items-center justify-center text-xs"
            >
              ✓
            </span>
          </div>
        </div>

        <footer class="p-4 border-t border-slate-800 flex items-center justify-between">
          <span class="text-xs text-slate-400">נבחרו: {{ importSelected.size }} תמונות</span>
          <div class="flex items-center gap-2">
            <button
              @click="showImportModal = false"
              class="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs cursor-pointer"
            >
              ביטול
            </button>
            <button
              @click="handleExecuteImport"
              :disabled="importSelected.size === 0 || isImporting"
              class="px-5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-bold text-xs transition cursor-pointer shadow-lg"
            >
              {{ isImporting ? 'מייבא...' : `הוסף ${importSelected.size} תמונות למאגר` }}
            </button>
          </div>
        </footer>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: CREATE SUB-GROUP                                  -->
    <!-- ======================================================== -->
    <div
      v-if="showCreateGroupModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
    >
      <div class="bg-slate-900 border border-slate-700 rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl">
        <h3 class="font-bold text-lg text-white">יצירת תת-קבוצה חדשה (ראש בראש)</h3>
        <p class="text-xs text-slate-400">
          תן שם לקבוצת התמונות המתחרות (למשל: "שלדג לבן-חזה - בחירת זווית").
        </p>
        <input
          v-model="newGroupName"
          type="text"
          placeholder="שם הקבוצה..."
          class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-purple-500"
          @keydown.enter="handleCreateGroup"
        />
        <div class="flex items-center gap-2">
          <label class="text-xs text-slate-400">שייך אל:</label>
          <select v-model="newGroupArea" class="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200">
            <option value="exhibition">תערוכה ראשית</option>
            <option value="wall">קיר תמונות</option>
          </select>
        </div>
        <div class="flex items-center justify-end gap-2 pt-2">
          <button @click="showCreateGroupModal = false" class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer">ביטול</button>
          <button @click="handleCreateGroup" :disabled="!newGroupName.trim()" class="px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs rounded-xl cursor-pointer">צור קבוצה</button>
        </div>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: GEMINI CRITIQUE & REVIEW                          -->
    <!-- ======================================================== -->
    <div
      v-if="activeCritiquePhoto"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
    >
      <div class="bg-slate-900 border border-indigo-500/40 rounded-3xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden shadow-2xl">
        <header class="p-5 border-b border-slate-800 flex items-center justify-between bg-indigo-950/30">
          <div class="flex items-center gap-2.5">
            <span class="text-xl">🤖</span>
            <div>
              <h3 class="font-bold text-base text-white">חוות דעת אוצר (Gemini AI)</h3>
              <p class="text-xs text-indigo-300">{{ activeCritiquePhoto.photo_data?.title }}</p>
            </div>
          </div>
          <button @click="activeCritiquePhoto = null" class="text-slate-400 hover:text-white p-1 cursor-pointer">✕</button>
        </header>

        <div class="flex-1 overflow-y-auto p-5 space-y-4">
          <div v-if="isAnalyzing" class="text-center py-12 space-y-3">
            <div class="w-8 h-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin mx-auto"></div>
            <p class="text-xs text-indigo-300">האוצר הדיגיטלי בוחן את הפריים, הקומפוזיציה והתאמתו לתערוכה...</p>
          </div>
          <div v-else class="text-xs sm:text-sm text-slate-200 leading-relaxed whitespace-pre-wrap bg-slate-950/50 p-4 rounded-xl border border-indigo-500/20">
            {{ activeCritiqueText || activeCritiquePhoto.ai_critique || 'לא נמצא ניתוח' }}
          </div>
        </div>

        <footer class="p-4 border-t border-slate-800 flex justify-end">
          <button @click="activeCritiquePhoto = null" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-xl cursor-pointer">
            סגור
          </button>
        </footer>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: GEMINI API KEY SETUP                              -->
    <!-- ======================================================== -->
    <div
      v-if="showApiKeyModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
    >
      <div class="bg-slate-900 border border-slate-700 rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl">
        <h3 class="font-bold text-lg text-white flex items-center gap-2">
          <span>🤖</span>
          <span>הגדרת Gemini API Key לאוצר הדיגיטלי</span>
        </h3>
        <p class="text-xs text-slate-400 leading-relaxed">
          מפתח זה מאפשר לג'ימיני לנתח את התצלומים, להעריך איכות הדפסה ולהכריע בתתי-קבוצות.
        </p>
        <input
          v-model="tempApiKey"
          type="password"
          placeholder="הדבק כאן מפתח (AIzaSy...)"
          class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-indigo-500"
        />
        <div class="flex items-center justify-end gap-2 pt-2">
          <button @click="showApiKeyModal = false" class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer">ביטול</button>
          <button @click="handleSaveApiKey" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-xl cursor-pointer">שמור מפתח</button>
        </div>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: SIMPLE PHOTO LIGHTBOX PREVIEW                     -->
    <!-- ======================================================== -->
    <div
      v-if="previewPhoto"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-xl"
      @click="previewPhoto = null"
    >
      <div class="relative max-w-4xl w-full max-h-[90vh] flex flex-col items-center" @click.stop>
        <button
          @click="previewPhoto = null"
          class="absolute -top-10 left-0 text-white text-lg hover:text-slate-300 cursor-pointer"
        >
          ✕ סגור
        </button>
        <img :src="previewPhoto.display || previewPhoto.thumbnail" class="max-h-[80vh] w-auto rounded-2xl shadow-2xl object-contain" />
        <div class="mt-3 text-center">
          <h4 class="text-base font-bold text-white">{{ previewPhoto.title }}</h4>
          <p class="text-xs text-sky-400">{{ previewPhoto.species_he }} • {{ previewPhoto.exif?.camera_model }}</p>
        </div>
      </div>
    </div>

  </div>
</template>
