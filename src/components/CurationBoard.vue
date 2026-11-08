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
  deleteSubGroup,
  assignPhotoToGroup,
  removePhotoFromGroup
} from '../utils/curationService.js';
import {
  getGeminiApiKey,
  saveGeminiApiKey,
  requestPhotoCritique,
  requestGroupComparison
} from '../utils/geminiCurator.js';
import CurationGroupCard from './CurationGroupCard.vue';

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
const newGroupStatus = ref('maybe'); // 'maybe' | 'sure' | 'pool'

// Sub-Group Decision / Alternative Choice Modal
const showDecisionModal = ref(false);
const activeDecisionGroup = ref(null);

// Assign Photo to Group Modal
const showAssignModal = ref(false);
const assigningPhoto = ref(null);
const assignSelectedGroupId = ref('');
const assignNewGroupName = ref('');

// Add Photo to Group Search (inside decision modal)
const showAddPhotoToGroupModal = ref(false);
const addPhotoSearch = ref('');

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
      // Link 2 / Score 2 (121 photos) -> 'maybe' (מועמדות אפשריות)
      // Link 1 / Score 1 (74 photos) -> 'pool' (מאגר לתערוכה)
      const status = score === 2 ? 'maybe' : 'pool';
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

// Filtered items: Candidate pool (maybe, pool) is SHARED between exhibition and photo wall!
// Only confirmed 'sure' items are filtered by activeArea (exhibition vs wall).
const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  return effectiveCurationItems.value.filter(item => {
    // If confirmed in sure, check if it matches current activeArea
    if (item.status === 'sure' && activeArea.value !== 'all') {
      const itemArea = item.area || 'exhibition';
      if (itemArea !== activeArea.value) return false;
    }
    // Search query match
    if (q) {
      const title = (item.photo_data?.title || '').toLowerCase();
      const species = (item.photo_data?.species_he || item.photo_data?.species_en || '').toLowerCase();
      if (!title.includes(q) && !species.includes(q)) return false;
    }
    return true;
  });
});

// Helper: get all photos assigned to a sub-group
const getGroupPhotos = (groupId) => {
  return effectiveCurationItems.value.filter(i => i.group_id === groupId);
};

// Helper: get the winning photo object for a sub-group (if chosen)
const getGroupWinnerPhoto = (group) => {
  if (!group || !group.winner_id) return null;
  return effectiveCurationItems.value.find(i => (i.photo_id === group.winner_id || i.id === group.winner_id)) || null;
};

// Sub-groups: Candidate pool is SHARED; only confirmed 'sure' groups are filtered by activeArea
const activeSubGroups = computed(() => {
  return subGroups.value.filter(g => {
    if (g.status === 'sure' && activeArea.value !== 'all') {
      const groupArea = g.area || 'exhibition';
      if (groupArea !== activeArea.value) return false;
    }
    return true;
  });
});

const activeGroupIds = computed(() => new Set(activeSubGroups.value.map(g => g.id)));

// Search filter for groups
const groupMatchesSearch = (group) => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return true;
  if ((group.name || '').toLowerCase().includes(q)) return true;
  const photos = getGroupPhotos(group.id);
  return photos.some(p => {
    const title = (p.photo_data?.title || '').toLowerCase();
    const species = (p.photo_data?.species_he || p.photo_data?.species_en || '').toLowerCase();
    return title.includes(q) || species.includes(q);
  });
};

// Sub-groups categorized by column status
const sureGroups = computed(() => {
  return activeSubGroups.value.filter(g => g.status === 'sure' && groupMatchesSearch(g));
});
const maybeGroups = computed(() => {
  return activeSubGroups.value.filter(g => (!g.status || g.status === 'maybe') && groupMatchesSearch(g));
});
const poolGroups = computed(() => {
  return activeSubGroups.value.filter(g => g.status === 'pool' && groupMatchesSearch(g));
});
const rejectedGroups = computed(() => {
  return activeSubGroups.value.filter(g => g.status === 'rejected' && groupMatchesSearch(g));
});

// Standalone photos per column (excluding photos that belong to an active sub-group)
const surePhotos = computed(() => {
  return filteredItems.value.filter(i => i.status === 'sure' && (!i.group_id || !activeGroupIds.value.has(i.group_id)));
});
const maybePhotos = computed(() => {
  return filteredItems.value.filter(i => i.status === 'maybe' && (!i.group_id || !activeGroupIds.value.has(i.group_id)));
});
const poolPhotos = computed(() => {
  return filteredItems.value.filter(i => (i.status === 'pool' || !i.status) && (!i.group_id || !activeGroupIds.value.has(i.group_id)));
});
const rejectedPhotos = computed(() => {
  return filteredItems.value.filter(i => i.status === 'rejected' && (!i.group_id || !activeGroupIds.value.has(i.group_id)));
});

// Total count per column (groups + standalone photos)
const sureCount = computed(() => sureGroups.value.length + surePhotos.value.length);
const maybeCount = computed(() => maybeGroups.value.length + maybePhotos.value.length);
const poolCount = computed(() => poolGroups.value.length + poolPhotos.value.length);
const rejectedCount = computed(() => rejectedGroups.value.length + rejectedPhotos.value.length);

// Backward-compatibility aliases
const sureItems = surePhotos;
const maybeItems = maybePhotos;
const poolItems = poolPhotos;
const rejectedItems = rejectedPhotos;
const groupItems = computed(() => filteredItems.value.filter(i => Boolean(i.group_id)));

// Multi-selection state for creating groups easily
const selectedPhotoIds = ref(new Set());
const showCreateGroupFromSelectionModal = ref(false);
const selectionGroupName = ref('');
const selectionGroupArea = ref('exhibition');
const selectionGroupStatus = ref('maybe'); // 'maybe' | 'sure' | 'pool'
const selectionExistingGroupId = ref('');

const isPhotoSelected = (photoId) => {
  return selectedPhotoIds.value.has(photoId);
};

const togglePhotoSelection = (photoId) => {
  const next = new Set(selectedPhotoIds.value);
  if (next.has(photoId)) {
    next.delete(photoId);
  } else {
    next.add(photoId);
  }
  selectedPhotoIds.value = next;
};

const clearSelection = () => {
  selectedPhotoIds.value = new Set();
};

const selectedPhotosList = computed(() => {
  return effectiveCurationItems.value.filter(i => selectedPhotoIds.value.has(i.photo_id || i.id));
});

const openCreateGroupFromSelection = () => {
  if (selectedPhotoIds.value.size === 0) return;
  const species = selectedPhotosList.value.map(p => p.photo_data?.species_he).filter(Boolean);
  const uniqueSpecies = [...new Set(species)];
  if (uniqueSpecies.length === 1) {
    selectionGroupName.value = `${uniqueSpecies[0]} - בחירה`;
  } else if (selectedPhotosList.value[0]?.photo_data?.title) {
    selectionGroupName.value = `${selectedPhotosList.value[0].photo_data.title} - חלופות`;
  } else {
    selectionGroupName.value = 'תת-קבוצה חדשה';
  }

  selectionGroupArea.value = activeArea.value === 'wall' ? 'wall' : 'exhibition';
  selectionGroupStatus.value = 'maybe';
  selectionExistingGroupId.value = '';
  showCreateGroupFromSelectionModal.value = true;
};

const handleConfirmCreateGroupFromSelection = async () => {
  if (selectedPhotoIds.value.size === 0) return;
  try {
    let targetGroupId = selectionExistingGroupId.value;
    let targetGroupName = '';

    if (!targetGroupId) {
      const name = selectionGroupName.value.trim() || 'תת-קבוצה חדשה';
      targetGroupId = await createSubGroup(name, selectionGroupArea.value, selectionGroupStatus.value);
      targetGroupName = name;
    } else {
      const existing = subGroups.value.find(g => g.id === targetGroupId);
      targetGroupName = existing ? existing.name : '';
    }

    for (const photoItem of selectedPhotosList.value) {
      await assignPhotoToGroup(
        photoItem.photo_id || photoItem.id,
        targetGroupId,
        targetGroupName,
        photoItem.photo_data
      );
    }

    clearSelection();
    showCreateGroupFromSelectionModal.value = false;
  } catch (err) {
    console.error('Group creation from selection error:', err);
  }
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

// Moving photo between statuses
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
    if (newStatus === 'sure') {
      updates.area = newArea || (activeArea.value === 'wall' ? 'wall' : 'exhibition');
    } else if (newArea) {
      updates.area = newArea;
    }
    await updateCurationStatus(photoId, updates, item?.photo_data);
  } catch (err) {
    console.error('Status update error:', err);
  }
};

// Moving group between columns
const handleMoveGroupStatus = async (groupId, newStatus, newArea = null) => {
  if (!isOwner.value) return;
  try {
    const updates = { status: newStatus };
    if (newStatus === 'sure') {
      updates.area = newArea || (activeArea.value === 'wall' ? 'wall' : 'exhibition');
    }
    await updateSubGroup(groupId, updates);
    const g = subGroups.value.find(x => x.id === groupId);
    if (g) {
      g.status = newStatus;
      if (updates.area) g.area = updates.area;
    }
  } catch (err) {
    console.error('Move group status error:', err);
  }
};

// Toggle item area between exhibition and wall
const handleToggleItemArea = async (photoId, currentArea) => {
  if (!isOwner.value) return;
  const nextArea = currentArea === 'wall' ? 'exhibition' : 'wall';
  await handleMoveStatus(photoId, 'sure', nextArea);
};

// Toggle group area between exhibition and wall
const handleToggleGroupArea = async (groupId, currentArea) => {
  if (!isOwner.value) return;
  const nextArea = currentArea === 'wall' ? 'exhibition' : 'wall';
  await handleMoveGroupStatus(groupId, 'sure', nextArea);
};

// Pick sub-group winner
const handleSelectGroupWinner = async (group, winnerPhoto) => {
  if (!isOwner.value) return;
  try {
    await updateSubGroup(group.id, { winner_id: winnerPhoto.id });
    group.winner_id = winnerPhoto.id;
  } catch (err) {
    console.error('Pick winner error:', err);
  }
};

// Clear group winner (revert to undecided)
const handleClearGroupWinner = async (group) => {
  if (!isOwner.value) return;
  try {
    await updateSubGroup(group.id, { winner_id: null });
    group.winner_id = null;
  } catch (err) {
    console.error('Clear winner error:', err);
  }
};

// Remove photo from group (make it standalone again)
const handleRemoveFromGroup = async (photoId) => {
  if (!isOwner.value) return;
  try {
    await removePhotoFromGroup(photoId);
    if (activeDecisionGroup.value && activeDecisionGroup.value.winner_id === photoId) {
      await updateSubGroup(activeDecisionGroup.value.id, { winner_id: null });
      activeDecisionGroup.value.winner_id = null;
    }
  } catch (err) {
    console.error('Remove from group error:', err);
  }
};

// Delete sub-group
const handleDeleteGroup = async (groupId) => {
  if (!isOwner.value) return;
  if (!confirm('האם אתה בטוח שברצונך לפרק תת-קבוצה זו? התמונות יישארו בלוח כעצמאיות.')) return;
  try {
    const photos = getGroupPhotos(groupId);
    for (const p of photos) {
      await removePhotoFromGroup(p.photo_id || p.id);
    }
    await deleteSubGroup(groupId);
    if (activeDecisionGroup.value?.id === groupId) {
      closeDecisionModal();
    }
  } catch (err) {
    console.error('Delete group error:', err);
  }
};

// Decision Modal openers
const openDecisionModal = (group) => {
  activeDecisionGroup.value = group;
  showDecisionModal.value = true;
};

const closeDecisionModal = () => {
  showDecisionModal.value = false;
  activeDecisionGroup.value = null;
};

// Assign Photo Modal openers
const openAssignPhotoModal = (photoItem) => {
  assigningPhoto.value = photoItem;
  assignSelectedGroupId.value = activeSubGroups.value[0]?.id || '';
  assignNewGroupName.value = '';
  showAssignModal.value = true;
};

const closeAssignModal = () => {
  showAssignModal.value = false;
  assigningPhoto.value = null;
};

const handleConfirmAssign = async () => {
  if (!assigningPhoto.value) return;
  try {
    let targetGroupId = assignSelectedGroupId.value;
    let targetGroupName = '';

    if (!targetGroupId && assignNewGroupName.value.trim()) {
      targetGroupId = await createSubGroup(
        assignNewGroupName.value.trim(),
        assigningPhoto.value.area || activeArea.value || 'exhibition',
        assigningPhoto.value.status || 'maybe'
      );
      targetGroupName = assignNewGroupName.value.trim();
    } else {
      const g = subGroups.value.find(x => x.id === targetGroupId);
      targetGroupName = g ? g.name : '';
    }

    if (targetGroupId) {
      await assignPhotoToGroup(
        assigningPhoto.value.photo_id || assigningPhoto.value.id,
        targetGroupId,
        targetGroupName,
        assigningPhoto.value.photo_data
      );
    }
    closeAssignModal();
  } catch (err) {
    console.error('Assign photo error:', err);
  }
};

// Add photo to active group inside decision modal
const addPhotosAvailable = computed(() => {
  if (!activeDecisionGroup.value) return [];
  const existingIds = new Set(getGroupPhotos(activeDecisionGroup.value.id).map(p => p.photo_id || p.id));
  const q = addPhotoSearch.value.trim().toLowerCase();
  return (props.initialPhotos || [])
    .filter(p => !existingIds.has(p.id))
    .filter(p => {
      if (!q) return true;
      const title = (p.title || p.ai?.title || '').toLowerCase();
      const species = (p.species_he || p.ai?.species_hebrew || '').toLowerCase();
      return title.includes(q) || species.includes(q);
    })
    .slice(0, 24);
});

const handleAddPhotoToActiveGroup = async (photo) => {
  if (!activeDecisionGroup.value || !isOwner.value) return;
  try {
    await assignPhotoToGroup(photo.id, activeDecisionGroup.value.id, activeDecisionGroup.value.name, {
      id: photo.id,
      title: photo.title || photo.filename,
      thumbnail: photo.thumb_url || photo.thumbnail,
      display: photo.display_url || photo.display,
      species_he: photo.species_he,
      species_en: photo.species_en,
      category: photo.category,
      exif: photo.exif || {}
    });
    showAddPhotoToGroupModal.value = false;
    addPhotoSearch.value = '';
  } catch (err) {
    console.error('Add photo to active group error:', err);
  }
};

// Drag & Drop
const draggedItem = ref(null); // { type: 'photo' | 'group', id: string }

const handleDragPhotoStart = (e, photoId) => {
  draggedItem.value = { type: 'photo', id: photoId };
  e.dataTransfer.effectAllowed = 'move';
};

const handleDragGroupStart = (e, groupId) => {
  draggedItem.value = { type: 'group', id: groupId };
  e.dataTransfer.effectAllowed = 'move';
};

const handleDrop = async (newStatus) => {
  if (!draggedItem.value || !isOwner.value) return;
  if (draggedItem.value.type === 'photo') {
    await handleMoveStatus(draggedItem.value.id, newStatus);
  } else if (draggedItem.value.type === 'group') {
    await handleMoveGroupStatus(draggedItem.value.id, newStatus);
  }
  draggedItem.value = null;
};

// Sub-group Creation
const handleCreateGroup = async () => {
  const name = newGroupName.value.trim();
  if (!name) return;
  try {
    await createSubGroup(name, newGroupArea.value, newGroupStatus.value);
    newGroupName.value = '';
    newGroupStatus.value = 'maybe';
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
              {{ (effectiveCurationItems.filter(i => i.area === 'exhibition' && (!i.group_id || !activeGroupIds.has(i.group_id))).length) + activeSubGroups.filter(g => g.area === 'exhibition').length }}
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
              {{ (effectiveCurationItems.filter(i => i.area === 'wall' && (!i.group_id || !activeGroupIds.has(i.group_id))).length) + activeSubGroups.filter(g => g.area === 'wall').length }}
            </span>
          </button>

          <button
            type="button"
            @click="activeArea = 'all'"
            class="px-3.5 py-2 rounded-lg text-xs font-medium transition cursor-pointer"
            :class="activeArea === 'all' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'"
          >
            <span>הכל ({{ (effectiveCurationItems.filter(i => !i.group_id || !activeGroupIds.has(i.group_id)).length) + activeSubGroups.length }})</span>
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
              <h3 class="font-bold text-amber-300 text-sm">
                {{ activeArea === 'wall' ? 'בטוחות לקיר התמונות' : (activeArea === 'exhibition' ? 'בטוחות לתערוכה ראשית' : 'מועמדות בטוחות') }}
              </h3>
            </div>
            <span class="px-2 py-0.5 bg-amber-950/80 text-amber-300 border border-amber-500/40 rounded-full text-xs font-bold font-mono">
              {{ sureCount }}
            </span>
          </div>

          <div class="space-y-3 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <!-- Group Candidates in Sure -->
            <CurationGroupCard
              v-for="group in sureGroups"
              :key="'group-' + group.id"
              :group="group"
              :photos="getGroupPhotos(group.id)"
              :winner="getGroupWinnerPhoto(group)"
              column="sure"
              :isOwner="isOwner"
              :currentUser="currentUser"
              @preview="previewPhoto = $event"
              @open-decision="openDecisionModal"
              @select-winner="({ group, photo }) => handleSelectGroupWinner(group, photo)"
              @clear-winner="handleClearGroupWinner"
              @compare-ai="handleCompareGroup"
              @move-status="({ groupId, newStatus }) => handleMoveGroupStatus(groupId, newStatus)"
              @drag-start="handleDragGroupStart"
              @vote="handleVote"
              @toggle-area="({ groupId, currentArea }) => handleToggleGroupArea(groupId, currentArea)"
            />

            <!-- Standalone Photos in Sure -->
            <div
              v-for="item in surePhotos"
              :key="item.id"
              :draggable="isOwner"
              @dragstart="handleDragPhotoStart($event, item.id)"
              class="group bg-slate-950 border rounded-xl p-3 space-y-2.5 transition shadow-lg relative"
              :class="isPhotoSelected(item.id) ? 'ring-2 ring-purple-500 border-purple-500 shadow-purple-900/40' : 'border-slate-800 hover:border-amber-500/50'"
            >
              <!-- Image Preview -->
              <div
                class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer"
                @click="previewPhoto = item.photo_data"
              >
                <img :src="item.photo_data?.thumbnail || item.photo_data?.display" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
                
                <!-- Multi-select checkbox button -->
                <button
                  type="button"
                  @click.stop="togglePhotoSelection(item.id)"
                  class="absolute top-2 left-2 z-20 w-6 h-6 rounded-lg flex items-center justify-center transition-all cursor-pointer shadow-md"
                  :class="isPhotoSelected(item.id)
                    ? 'bg-purple-600 text-white ring-2 ring-purple-400 scale-110 shadow-purple-500/50'
                    : 'bg-slate-950/80 hover:bg-purple-900/60 text-slate-400 hover:text-purple-200 border border-slate-700/80'"
                  :title="isPhotoSelected(item.id) ? 'בטל סימון' : 'סמן לאיחוד בקבוצה'"
                >
                  <span v-if="isPhotoSelected(item.id)" class="text-xs font-black">✓</span>
                  <span v-else class="text-[11px] font-bold">+</span>
                </button>

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
                <div class="flex items-center justify-between gap-1">
                  <h4 class="text-xs font-bold text-slate-100 truncate">{{ item.photo_data?.title }}</h4>
                  <!-- Area Badge / Switcher -->
                  <button
                    v-if="isOwner"
                    type="button"
                    @click="handleToggleItemArea(item.id, item.area || 'exhibition')"
                    class="px-1.5 py-0.2 rounded text-[9px] font-bold shrink-0 transition"
                    :class="(item.area || 'exhibition') === 'wall' ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/30' : 'bg-indigo-950/80 text-indigo-300 border border-indigo-500/30'"
                    :title="'לחץ להעברה אל ' + ((item.area || 'exhibition') === 'wall' ? 'תערוכה ראשית' : 'קיר תמונות')"
                  >
                    {{ (item.area || 'exhibition') === 'wall' ? '🧱 קיר' : '🖼️ תערוכה' }} ⇄
                  </button>
                </div>
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
                  @click="togglePhotoSelection(item.id)"
                  class="text-purple-400 hover:text-purple-200 cursor-pointer flex items-center gap-0.5 font-semibold"
                  title="סמן תמונה זו לאיחוד בקבוצה"
                >
                  <span>{{ isPhotoSelected(item.id) ? '✓ סומן' : '+ סמן לקבוצה' }}</span>
                </button>
                <button
                  type="button"
                  @click="handleMoveStatus(item.id, 'pool')"
                  class="hover:text-slate-200 cursor-pointer"
                >
                  למאגר ➡
                </button>
              </div>
            </div>

            <div v-if="sureCount === 0" class="text-center py-12 px-2 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl space-y-1">
              <p>טרם נבחרו מועמדות סופיות.</p>
              <p class="text-[10px] text-slate-600">סמן תמונות, גרור לכאן, או לחץ ״🌟 קדם לבטוחה״ מתוך המועמדות האפשריות.</p>
            </div>
          </div>
        </div>

        <!-- Column 2: 🤔 מועמדות אפשריות (Maybe) -->
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
              {{ maybeCount }}
            </span>
          </div>

          <div class="space-y-3 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <!-- Group Candidates in Maybe -->
            <CurationGroupCard
              v-for="group in maybeGroups"
              :key="'group-' + group.id"
              :group="group"
              :photos="getGroupPhotos(group.id)"
              :winner="getGroupWinnerPhoto(group)"
              column="maybe"
              :isOwner="isOwner"
              :currentUser="currentUser"
              @preview="previewPhoto = $event"
              @open-decision="openDecisionModal"
              @select-winner="({ group, photo }) => handleSelectGroupWinner(group, photo)"
              @clear-winner="handleClearGroupWinner"
              @compare-ai="handleCompareGroup"
              @move-status="({ groupId, newStatus }) => handleMoveGroupStatus(groupId, newStatus)"
              @drag-start="handleDragGroupStart"
              @vote="handleVote"
              @toggle-area="({ groupId, currentArea }) => handleToggleGroupArea(groupId, currentArea)"
            />

            <!-- Standalone Photos in Maybe -->
            <div
              v-for="item in maybePhotos"
              :key="item.id"
              :draggable="isOwner"
              @dragstart="handleDragPhotoStart($event, item.id)"
              class="group bg-slate-950 border rounded-xl p-3 space-y-2.5 transition shadow-lg relative"
              :class="isPhotoSelected(item.id) ? 'ring-2 ring-purple-500 border-purple-500 shadow-purple-900/40' : 'border-slate-800 hover:border-sky-500/50'"
            >
              <div
                class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer"
                @click="previewPhoto = item.photo_data"
              >
                <img :src="item.photo_data?.thumbnail || item.photo_data?.display" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
                
                <!-- Multi-select checkbox button -->
                <button
                  type="button"
                  @click.stop="togglePhotoSelection(item.id)"
                  class="absolute top-2 left-2 z-20 w-6 h-6 rounded-lg flex items-center justify-center transition-all cursor-pointer shadow-md"
                  :class="isPhotoSelected(item.id)
                    ? 'bg-purple-600 text-white ring-2 ring-purple-400 scale-110 shadow-purple-500/50'
                    : 'bg-slate-950/80 hover:bg-purple-900/60 text-slate-400 hover:text-purple-200 border border-slate-700/80'"
                  :title="isPhotoSelected(item.id) ? 'בטל סימון' : 'סמן לאיחוד בקבוצה'"
                >
                  <span v-if="isPhotoSelected(item.id)" class="text-xs font-black">✓</span>
                  <span v-else class="text-[11px] font-bold">+</span>
                </button>

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
                <button type="button" @click="handleMoveStatus(item.id, 'sure')" class="text-amber-300 hover:underline cursor-pointer font-bold">
                  🌟 קדם לבטוחה
                </button>
                <button
                  type="button"
                  @click="togglePhotoSelection(item.id)"
                  class="text-purple-400 hover:text-purple-200 cursor-pointer flex items-center gap-0.5 font-semibold"
                  title="סמן תמונה זו לאיחוד בקבוצה"
                >
                  <span>{{ isPhotoSelected(item.id) ? '✓ סומן' : '+ סמן לקבוצה' }}</span>
                </button>
                <button type="button" @click="handleMoveStatus(item.id, 'pool')" class="text-slate-400 hover:underline cursor-pointer">
                  העבר למאגר ➡
                </button>
              </div>
            </div>

            <div v-if="maybeCount === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
              אין מועמדות אפשריות כרגע
            </div>
          </div>
        </div>

        <!-- Column 3: 📥 מאגר לתערוכה (Pool) -->
        <div
          class="bg-slate-900/60 border border-slate-700/60 rounded-2xl p-4 flex flex-col space-y-3 backdrop-blur-md"
          @dragover.prevent
          @drop="handleDrop('pool')"
        >
          <div class="flex items-center justify-between pb-2 border-b border-slate-700/40">
            <div class="flex items-center gap-2">
              <span class="text-base">📥</span>
              <h3 class="font-bold text-slate-200 text-sm">מאגר לתערוכה</h3>
            </div>
            <span class="px-2 py-0.5 bg-slate-800 text-slate-300 border border-slate-700 rounded-full text-xs font-bold font-mono">
              {{ poolCount }}
            </span>
          </div>

          <p class="text-[11px] text-slate-400">
            תמונות נוספות מועמדות לתערוכה (קישור 1). ניתן לקדם לאפשרית או לבטוחה.
          </p>

          <div class="space-y-3 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <!-- Group Candidates in Pool -->
            <CurationGroupCard
              v-for="group in poolGroups"
              :key="'group-' + group.id"
              :group="group"
              :photos="getGroupPhotos(group.id)"
              :winner="getGroupWinnerPhoto(group)"
              column="pool"
              :isOwner="isOwner"
              :currentUser="currentUser"
              @preview="previewPhoto = $event"
              @open-decision="openDecisionModal"
              @select-winner="({ group, photo }) => handleSelectGroupWinner(group, photo)"
              @clear-winner="handleClearGroupWinner"
              @compare-ai="handleCompareGroup"
              @move-status="({ groupId, newStatus }) => handleMoveGroupStatus(groupId, newStatus)"
              @drag-start="handleDragGroupStart"
              @vote="handleVote"
              @toggle-area="({ groupId, currentArea }) => handleToggleGroupArea(groupId, currentArea)"
            />

            <!-- Standalone Photos in Pool -->
            <div
              v-for="item in poolPhotos"
              :key="item.id"
              :draggable="isOwner"
              @dragstart="handleDragPhotoStart($event, item.id)"
              class="group bg-slate-950 border rounded-xl p-3 space-y-2.5 transition shadow-lg relative"
              :class="isPhotoSelected(item.id) ? 'ring-2 ring-purple-500 border-purple-500 shadow-purple-900/40' : 'border-slate-800 hover:border-slate-600'"
            >
              <div
                class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 cursor-pointer"
                @click="previewPhoto = item.photo_data"
              >
                <img :src="item.photo_data?.thumbnail || item.photo_data?.display" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
                
                <!-- Multi-select checkbox button -->
                <button
                  type="button"
                  @click.stop="togglePhotoSelection(item.id)"
                  class="absolute top-2 left-2 z-20 w-6 h-6 rounded-lg flex items-center justify-center transition-all cursor-pointer shadow-md"
                  :class="isPhotoSelected(item.id)
                    ? 'bg-purple-600 text-white ring-2 ring-purple-400 scale-110 shadow-purple-500/50'
                    : 'bg-slate-950/80 hover:bg-purple-900/60 text-slate-400 hover:text-purple-200 border border-slate-700/80'"
                  :title="isPhotoSelected(item.id) ? 'בטל סימון' : 'סמן לאיחוד בקבוצה'"
                >
                  <span v-if="isPhotoSelected(item.id)" class="text-xs font-black">✓</span>
                  <span v-else class="text-[11px] font-bold">+</span>
                </button>

                <span class="absolute top-2 right-2 px-2 py-0.5 bg-slate-950/80 backdrop-blur-md rounded-full text-[10px] text-slate-300 border border-slate-700 font-bold">
                  {{ item.photo_data?.species_he || 'תמונה' }}
                </span>
                <span
                  class="absolute bottom-2 left-2 px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1 shadow-md bg-slate-900 text-slate-300 border border-slate-700"
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

              <div v-if="isOwner" class="pt-1 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-900">
                <button type="button" @click="handleMoveStatus(item.id, 'maybe')" class="text-sky-300 hover:underline cursor-pointer">
                  🤔 קדם לאפשרית ⬅
                </button>
                <button
                  type="button"
                  @click="togglePhotoSelection(item.id)"
                  class="text-purple-400 hover:text-purple-200 cursor-pointer flex items-center gap-0.5 font-semibold"
                  title="סמן תמונה זו לאיחוד בקבוצה"
                >
                  <span>{{ isPhotoSelected(item.id) ? '✓ סומן' : '+ סמן לקבוצה' }}</span>
                </button>
                <button type="button" @click="handleMoveStatus(item.id, 'sure')" class="text-amber-300 hover:underline cursor-pointer">
                  🌟 בטוחה ⬅
                </button>
              </div>
            </div>

            <div v-if="poolCount === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
              אין תמונות במאגר כרגע
            </div>
          </div>
        </div>

        <!-- Column 4: ❌ נפסלו / בארכיון (Rejected) -->
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
              {{ rejectedCount }}
            </span>
          </div>

          <div class="space-y-2.5 flex-1 overflow-y-auto max-h-[75vh] pr-1">
            <!-- Group Candidates in Rejected -->
            <CurationGroupCard
              v-for="group in rejectedGroups"
              :key="'group-' + group.id"
              :group="group"
              :photos="getGroupPhotos(group.id)"
              :winner="getGroupWinnerPhoto(group)"
              column="rejected"
              :isOwner="isOwner"
              :currentUser="currentUser"
              @preview="previewPhoto = $event"
              @open-decision="openDecisionModal"
              @select-winner="({ group, photo }) => handleSelectGroupWinner(group, photo)"
              @clear-winner="handleClearGroupWinner"
              @compare-ai="handleCompareGroup"
              @move-status="({ groupId, newStatus }) => handleMoveGroupStatus(groupId, newStatus)"
              @drag-start="handleDragGroupStart"
              @vote="handleVote"
              @toggle-area="({ groupId, currentArea }) => handleToggleGroupArea(groupId, currentArea)"
            />

            <!-- Standalone Photos in Rejected -->
            <div
              v-for="item in rejectedPhotos"
              :key="item.id"
              class="flex items-center gap-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-2"
            >
              <img :src="item.photo_data?.thumbnail" class="w-12 h-12 rounded-lg object-cover cursor-pointer shrink-0 filter grayscale hover:grayscale-0 transition" @click="previewPhoto = item.photo_data" />
              <div class="flex-1 min-w-0">
                <h4 class="text-xs text-slate-300 truncate">{{ item.photo_data?.title }}</h4>
                <p class="text-[10px] text-slate-500 truncate">{{ item.photo_data?.species_he }}</p>
              </div>
              <div v-if="isOwner" class="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  @click="handleMoveStatus(item.id, 'maybe')"
                  class="text-xs text-sky-400 hover:text-white px-2 py-1 bg-slate-800 rounded cursor-pointer"
                  title="החזר לאפשרית"
                >
                  ↩
                </button>
              </div>
            </div>

            <div v-if="rejectedCount === 0" class="text-center py-12 text-xs text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
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
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="text-[11px] text-slate-400">שייך אל:</label>
            <select v-model="newGroupArea" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200">
              <option value="exhibition">תערוכה ראשית</option>
              <option value="wall">קיר תמונות</option>
            </select>
          </div>
          <div class="space-y-1">
            <label class="text-[11px] text-slate-400">הצב בטור:</label>
            <select v-model="newGroupStatus" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200">
              <option value="maybe">🤔 מועמדות אפשריות</option>
              <option value="sure">🌟 מועמדות בטוחות</option>
              <option value="pool">📥 מאגר לתערוכה</option>
            </select>
          </div>
        </div>
        <div class="flex items-center justify-end gap-2 pt-2">
          <button @click="showCreateGroupModal = false" class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer">ביטול</button>
          <button @click="handleCreateGroup" :disabled="!newGroupName.trim()" class="px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs rounded-xl cursor-pointer">צור קבוצה</button>
        </div>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: DECISION & ALTERNATIVE SELECTION IN SUB-GROUP     -->
    <!-- ======================================================== -->
    <div
      v-if="showDecisionModal && activeDecisionGroup"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md"
      @click="closeDecisionModal"
    >
      <div
        class="bg-slate-900 border border-purple-500/40 rounded-3xl max-w-5xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl"
        @click.stop
      >
        <!-- Modal Header -->
        <header class="p-5 border-b border-slate-800 flex items-center justify-between bg-purple-950/20">
          <div class="flex items-center gap-3">
            <span class="text-2xl">⚔️</span>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-lg text-white">{{ activeDecisionGroup.name }}</h3>
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-bold"
                  :class="activeDecisionGroup.winner_id ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40' : 'bg-purple-900/60 text-purple-300 border border-purple-500/30'"
                >
                  {{ activeDecisionGroup.winner_id ? '✓ הוכרעה מנצחת' : '🤔 טרם הוכרע' }}
                </span>
              </div>
              <p class="text-xs text-purple-300">
                {{ getGroupPhotos(activeDecisionGroup.id).length }} תמונות מתחרות על משבצת זו • לחץ ״בחר כמנצחת״ להכרעה
              </p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <!-- AI Compare button inside modal -->
            <button
              type="button"
              @click="handleCompareGroup(activeDecisionGroup)"
              class="px-3 py-1.5 rounded-xl bg-indigo-950 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-900/80 text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer"
            >
              <span>🤖</span>
              <span>שאל את ג'ימיני מי המנצחת</span>
            </button>
            <button @click="closeDecisionModal" class="text-slate-400 hover:text-white p-1 cursor-pointer text-lg">✕</button>
          </div>
        </header>

        <!-- AI Comparison Result if available -->
        <div v-if="activeDecisionGroup.ai_comparison" class="px-5 pt-4">
          <div class="bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-3 text-xs text-indigo-100 leading-relaxed space-y-1">
            <div class="font-bold text-indigo-300 flex items-center gap-1.5">
              <span>🤖</span>
              <span>המלצת ג'ימיני לתערוכה:</span>
            </div>
            <p class="whitespace-pre-wrap">{{ activeDecisionGroup.ai_comparison }}</p>
          </div>
        </div>

        <!-- Photos Comparison Grid -->
        <div class="flex-1 overflow-y-auto p-5">
          <div v-if="getGroupPhotos(activeDecisionGroup.id).length === 0" class="text-center py-16 text-slate-500 text-xs space-y-2">
            <p>אין תמונות בקבוצה זו כרגע.</p>
            <button
              v-if="isOwner"
              type="button"
              @click="showAddPhotoToGroupModal = true"
              class="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-bold cursor-pointer"
            >
              + צרף תמונה מתמונות הגלריה
            </button>
          </div>

          <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            <div
              v-for="photo in getGroupPhotos(activeDecisionGroup.id)"
              :key="photo.id"
              class="bg-slate-950 rounded-2xl border p-3.5 space-y-3 transition relative shadow-lg"
              :class="activeDecisionGroup.winner_id === photo.id ? 'border-amber-400 ring-2 ring-amber-400/40 bg-gradient-to-b from-amber-950/20 to-slate-950' : 'border-slate-800 hover:border-slate-700'"
            >
              <!-- Winner Crown / Status Badge -->
              <div v-if="activeDecisionGroup.winner_id === photo.id" class="absolute -top-3 -right-2 z-10 px-2.5 py-0.5 bg-amber-500 text-slate-950 font-black rounded-full text-xs shadow-lg flex items-center gap-1">
                <span>👑 המנצחת שנבחרה!</span>
              </div>

              <!-- Media Preview -->
              <div
                class="relative aspect-[3/2] rounded-xl overflow-hidden bg-slate-900 cursor-pointer"
                @click="previewPhoto = photo.photo_data"
              >
                <img :src="photo.photo_data?.thumbnail || photo.photo_data?.display" class="w-full h-full object-cover hover:scale-105 transition duration-300" />
                <span class="absolute top-2 right-2 px-2 py-0.5 bg-slate-950/80 backdrop-blur-md rounded-full text-[10px] text-purple-300 border border-purple-500/40 font-bold">
                  {{ photo.photo_data?.species_he || 'תמונה' }}
                </span>
                <span
                  class="absolute bottom-2 left-2 px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1 shadow-md bg-slate-900 text-slate-300 border border-slate-700"
                >
                  <span>ציון:</span>
                  <span class="font-mono">{{ calculateScore(photo.votes) }}</span>
                </span>
              </div>

              <!-- Title & EXIF -->
              <div>
                <h4 class="text-sm font-bold text-white truncate">{{ photo.photo_data?.title }}</h4>
                <p class="text-xs text-slate-400 truncate">
                  {{ photo.photo_data?.exif?.camera_model }} • {{ photo.photo_data?.exif?.lens_model }}
                </p>
                <p v-if="photo.photo_data?.humorous_description" class="text-[11px] text-purple-300 italic mt-1 line-clamp-2">
                  "{{ photo.photo_data?.humorous_description }}"
                </p>
              </div>

              <!-- Voting buttons inside modal -->
              <div class="flex items-center justify-between bg-slate-900/80 p-1.5 rounded-lg border border-slate-800 text-xs">
                <button @click="handleVote(photo.id, 2)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-amber-400 bg-amber-500/20': currentUser && photo.votes?.[currentUser.uid]?.score === 2 }" title="🔥 חובה (+2)">🔥</button>
                <button @click="handleVote(photo.id, 1)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-emerald-400 bg-emerald-500/20': currentUser && photo.votes?.[currentUser.uid]?.score === 1 }" title="👍 מוצלחת (+1)">👍</button>
                <button @click="handleVote(photo.id, 0)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-slate-400 bg-slate-700': currentUser && photo.votes?.[currentUser.uid]?.score === 0 }" title="🤔 מתלבט (0)">🤔</button>
                <button @click="handleVote(photo.id, -1)" class="p-1 rounded hover:bg-slate-800 cursor-pointer" :class="{ 'ring-1 ring-rose-400 bg-rose-500/20': currentUser && photo.votes?.[currentUser.uid]?.score === -1 }" title="👎 פחות מתאים (-1)">👎</button>
                <span class="text-[10px] text-slate-400 font-mono pr-1">({{ countVotes(photo.votes) }})</span>
              </div>

              <!-- Decision Selection Action (Owner only) -->
              <div v-if="isOwner" class="space-y-1.5 pt-1">
                <button
                  v-if="activeDecisionGroup.winner_id === photo.id"
                  type="button"
                  @click="handleClearGroupWinner(activeDecisionGroup)"
                  class="w-full py-2 bg-amber-500 text-slate-950 font-bold text-xs rounded-xl hover:bg-amber-400 transition cursor-pointer flex items-center justify-center gap-1.5 shadow-md"
                >
                  <span>✓ נבחרה כמנצחת (לחץ לביטול)</span>
                </button>
                <button
                  v-else
                  type="button"
                  @click="handleSelectGroupWinner(activeDecisionGroup, photo)"
                  class="w-full py-2 bg-purple-600/30 hover:bg-purple-600 text-purple-200 hover:text-white border border-purple-500/40 font-bold text-xs rounded-xl transition cursor-pointer flex items-center justify-center gap-1.5"
                >
                  <span>🏆 בחר בתמונה זו כמנצחת</span>
                </button>

                <div class="flex items-center justify-end pt-1">
                  <button
                    type="button"
                    @click="handleRemoveFromGroup(photo.photo_id || photo.id)"
                    class="text-[11px] text-slate-400 hover:text-rose-400 transition cursor-pointer"
                  >
                    ✕ הסר מתת-קבוצה זו
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Modal Footer -->
        <footer class="p-4 border-t border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div class="flex items-center gap-2">
            <button
              v-if="isOwner"
              type="button"
              @click="showAddPhotoToGroupModal = true"
              class="px-3.5 py-2 rounded-xl bg-purple-600/30 hover:bg-purple-600/60 text-purple-200 border border-purple-500/40 text-xs font-semibold transition cursor-pointer flex items-center gap-1"
            >
              <span>➕</span>
              <span>צרף תמונה נוספת</span>
            </button>
            <button
              v-if="isOwner"
              type="button"
              @click="handleDeleteGroup(activeDecisionGroup.id)"
              class="px-3 py-2 rounded-xl text-rose-400 hover:bg-rose-950/40 text-xs transition cursor-pointer"
            >
              🗑️ פרק תת-קבוצה
            </button>
          </div>

          <button
            type="button"
            @click="closeDecisionModal"
            class="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs rounded-xl cursor-pointer"
          >
            סגור
          </button>
        </footer>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: ASSIGN A PHOTO TO A SUB-GROUP                     -->
    <!-- ======================================================== -->
    <div
      v-if="showAssignModal && assigningPhoto"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
      @click="closeAssignModal"
    >
      <div
        class="bg-slate-900 border border-purple-500/40 rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl"
        @click.stop
      >
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-2">
            <span class="text-xl">⚔️</span>
            <h3 class="font-bold text-base text-white">צירוף תמונה לתת-קבוצה (ראש בראש)</h3>
          </div>
          <button @click="closeAssignModal" class="text-slate-400 hover:text-white cursor-pointer">✕</button>
        </div>

        <!-- Photo being assigned preview -->
        <div class="flex items-center gap-3 bg-slate-950 p-2.5 rounded-xl border border-slate-800">
          <img :src="assigningPhoto.photo_data?.thumbnail" class="w-14 h-14 rounded-lg object-cover" />
          <div class="min-w-0">
            <h4 class="text-xs font-bold text-white truncate">{{ assigningPhoto.photo_data?.title }}</h4>
            <p class="text-[10px] text-slate-400">{{ assigningPhoto.photo_data?.species_he }}</p>
          </div>
        </div>

        <!-- Option 1: Existing Group -->
        <div v-if="activeSubGroups.length > 0" class="space-y-1.5">
          <label class="text-xs text-slate-300 font-semibold">בחר תת-קבוצה קיימת:</label>
          <select
            v-model="assignSelectedGroupId"
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-purple-500"
          >
            <option value="">-- בחר קבוצה --</option>
            <option v-for="g in activeSubGroups" :key="g.id" :value="g.id">
              {{ g.name }} ({{ getGroupPhotos(g.id).length }} תמונות)
            </option>
          </select>
        </div>

        <div class="text-center text-xs text-slate-500">או</div>

        <!-- Option 2: Create New Group -->
        <div class="space-y-1.5">
          <label class="text-xs text-slate-300 font-semibold">צור תת-קבוצה חדשה עם תמונה זו:</label>
          <input
            v-model="assignNewGroupName"
            type="text"
            placeholder="לדוגמה: שלדג לבן-חזה - בחירת תנוחה"
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-purple-500"
          />
        </div>

        <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
          <button @click="closeAssignModal" class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer">ביטול</button>
          <button
            @click="handleConfirmAssign"
            :disabled="!assignSelectedGroupId && !assignNewGroupName.trim()"
            class="px-5 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white font-bold text-xs rounded-xl cursor-pointer"
          >
            שייך לתת-קבוצה
          </button>
        </div>
      </div>
    </div>

    <!-- ======================================================== -->
    <!-- MODAL: ADD PHOTO SEARCH (INSIDE DECISION MODAL)           -->
    <!-- ======================================================== -->
    <div
      v-if="showAddPhotoToGroupModal && activeDecisionGroup"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md"
      @click="showAddPhotoToGroupModal = false"
    >
      <div
        class="bg-slate-900 border border-purple-500/40 rounded-3xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden shadow-2xl"
        @click.stop
      >
        <header class="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 class="font-bold text-base text-white">הוספת תמונה לתת-הקבוצה ״{{ activeDecisionGroup.name }}״</h3>
          <button @click="showAddPhotoToGroupModal = false" class="text-slate-400 hover:text-white cursor-pointer">✕</button>
        </header>

        <div class="p-4 border-b border-slate-800">
          <input
            v-model="addPhotoSearch"
            type="text"
            placeholder="חפש לפי שם תמונה או חיה (למשל: ינשוף, שלדג)..."
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
        </div>

        <div class="flex-1 overflow-y-auto p-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div
            v-for="photo in addPhotosAvailable"
            :key="photo.id"
            @click="handleAddPhotoToActiveGroup(photo)"
            class="group bg-slate-950 border border-slate-800 hover:border-purple-500 rounded-xl p-2 space-y-1.5 cursor-pointer transition"
          >
            <div class="aspect-[3/2] rounded-lg overflow-hidden bg-slate-900">
              <img :src="photo.thumb_url || photo.thumbnail || photo.paths?.thumbnail" class="w-full h-full object-cover group-hover:scale-105 transition" />
            </div>
            <h5 class="text-xs font-bold text-white truncate">{{ photo.title || photo.filename }}</h5>
            <p class="text-[10px] text-slate-400 truncate">{{ photo.species_he }}</p>
            <button
              type="button"
              class="w-full py-1 bg-purple-600/30 group-hover:bg-purple-600 text-purple-200 group-hover:text-white rounded text-[10px] font-semibold transition"
            >
              + צרף
            </button>
          </div>
        </div>

        <footer class="p-3 border-t border-slate-800 flex justify-end">
          <button @click="showAddPhotoToGroupModal = false" class="px-4 py-1.5 bg-slate-800 text-slate-300 rounded-xl text-xs cursor-pointer">
            סגור
          </button>
        </footer>
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

    <!-- ======================================================== -->
    <!-- FLOATING MULTI-SELECT BAR (BOTTOM OF SCREEN)             -->
    <!-- ======================================================== -->
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform translate-y-20 opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform translate-y-20 opacity-0"
    >
      <div
        v-if="selectedPhotoIds.size > 0"
        class="fixed bottom-6 inset-x-0 z-40 max-w-xl mx-auto px-4"
      >
        <div class="bg-slate-900/95 border border-purple-500/50 backdrop-blur-xl rounded-2xl p-3 shadow-2xl flex items-center justify-between gap-3 ring-1 ring-purple-500/30">
          <div class="flex items-center gap-3 min-w-0">
            <!-- Count badge -->
            <span class="px-2.5 py-1 bg-purple-600 text-white font-black rounded-xl text-xs shrink-0 shadow">
              {{ selectedPhotoIds.size }} נבחרו
            </span>

            <!-- Mini thumbnail previews of selected photos -->
            <div class="flex items-center -space-x-2 space-x-reverse overflow-hidden py-0.5">
              <img
                v-for="p in selectedPhotosList.slice(0, 5)"
                :key="p.id"
                :src="p.photo_data?.thumbnail"
                class="w-8 h-8 rounded-full object-cover border-2 border-slate-900 shrink-0 shadow"
              />
              <span
                v-if="selectedPhotosList.length > 5"
                class="w-8 h-8 rounded-full bg-slate-800 text-slate-300 border-2 border-slate-900 flex items-center justify-center text-[10px] font-bold shrink-0"
              >
                +{{ selectedPhotosList.length - 5 }}
              </span>
            </div>
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <!-- Action Button: Create Group -->
            <button
              type="button"
              @click="openCreateGroupFromSelection"
              class="px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs rounded-xl shadow-lg transition cursor-pointer flex items-center gap-1.5"
            >
              <span>⚔️</span>
              <span>צור תת-קבוצה...</span>
            </button>

            <!-- Clear Selection -->
            <button
              type="button"
              @click="clearSelection"
              class="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition cursor-pointer text-xs"
              title="בטל סימון"
            >
              ✕
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- ======================================================== -->
    <!-- MODAL: CREATE SUB-GROUP FROM SELECTED PHOTOS             -->
    <!-- ======================================================== -->
    <div
      v-if="showCreateGroupFromSelectionModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md"
      @click="showCreateGroupFromSelectionModal = false"
    >
      <div
        class="bg-slate-900 border border-purple-500/50 rounded-3xl max-w-lg w-full p-6 space-y-4 shadow-2xl"
        @click.stop
      >
        <!-- Header -->
        <div class="flex items-center justify-between pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2">
            <span class="text-2xl">⚔️</span>
            <div>
              <h3 class="font-bold text-lg text-white">איחוד {{ selectedPhotosList.length }} תמונות לתת-קבוצה</h3>
              <p class="text-xs text-purple-300">התמונות יוצגו כמשבצת אחת בלוח ויתחרו ראש בראש</p>
            </div>
          </div>
          <button @click="showCreateGroupFromSelectionModal = false" class="text-slate-400 hover:text-white cursor-pointer">✕</button>
        </div>

        <!-- Selected Photos Preview Grid -->
        <div class="grid grid-cols-4 gap-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800 max-h-36 overflow-y-auto">
          <div
            v-for="p in selectedPhotosList"
            :key="p.id"
            class="relative aspect-[3/2] rounded-lg overflow-hidden bg-slate-900 border border-slate-800"
          >
            <img :src="p.photo_data?.thumbnail" class="w-full h-full object-cover" />
            <span class="absolute bottom-0 inset-x-0 bg-black/70 text-[9px] text-white truncate px-1">
              {{ p.photo_data?.title }}
            </span>
          </div>
        </div>

        <!-- Form: Name -->
        <div class="space-y-1">
          <label class="text-xs font-semibold text-slate-300">שם תת-הקבוצה:</label>
          <input
            v-model="selectionGroupName"
            type="text"
            placeholder="לדוגמה: שלדג לבן-חזה - בחירת תנוחה"
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-purple-500"
            @keydown.enter="handleConfirmCreateGroupFromSelection"
          />
        </div>

        <!-- Form: Where to place it (Column & Area) -->
        <div class="grid grid-cols-2 gap-3 pt-1">
          <div class="space-y-1">
            <label class="text-xs font-semibold text-slate-300">איפה למקם בלוח?</label>
            <select
              v-model="selectionGroupStatus"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-purple-500"
            >
              <option value="maybe">🤔 מועמדות אפשריות (מומלץ)</option>
              <option value="sure">🌟 מועמדות בטוחות</option>
              <option value="pool">📥 מאגר לתערוכה</option>
            </select>
          </div>

          <div class="space-y-1">
            <label class="text-xs font-semibold text-slate-300">שייך אל:</label>
            <select
              v-model="selectionGroupArea"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-purple-500"
            >
              <option value="exhibition">🖼️ תערוכה ראשית</option>
              <option value="wall">🧱 קיר תמונות</option>
            </select>
          </div>
        </div>

        <!-- Existing Group Alternative (if groups exist) -->
        <div v-if="activeSubGroups.length > 0" class="pt-2 border-t border-slate-800 space-y-1">
          <label class="text-[11px] text-slate-400">או הוסף לתת-קבוצה קיימת:</label>
          <select
            v-model="selectionExistingGroupId"
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-300"
          >
            <option value="">-- בחר קבוצה קיימת במקום ליצור חדשה --</option>
            <option v-for="g in activeSubGroups" :key="g.id" :value="g.id">
              {{ g.name }} ({{ getGroupPhotos(g.id).length }} תמונות)
            </option>
          </select>
        </div>

        <!-- Footer Actions -->
        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
          <button
            @click="showCreateGroupFromSelectionModal = false"
            class="px-4 py-2 text-xs text-slate-400 hover:text-white cursor-pointer"
          >
            ביטול
          </button>
          <button
            @click="handleConfirmCreateGroupFromSelection"
            :disabled="!selectionGroupName.trim() && !selectionExistingGroupId"
            class="px-5 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:opacity-40 text-white font-bold text-xs rounded-xl shadow-lg transition cursor-pointer"
          >
            {{ selectionExistingGroupId ? 'הוסף לקבוצה קיימת' : 'צור תת-קבוצה ואחד' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>
