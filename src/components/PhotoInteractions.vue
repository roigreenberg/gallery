<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue';
import {
  auth,
  subscribeToAuth,
  loginWithGoogle,
  isUserOwner
} from '../utils/firebase.js';
import {
  togglePhotoLike,
  subscribeToPhotoLikes,
  addPhotoComment,
  subscribeToPhotoComments,
  deletePhotoComment
} from '../utils/interactionsService.js';
import { addPhotoToCuration } from '../utils/curationService.js';

const props = defineProps({
  photo: {
    type: Object,
    required: true
  },
  currentLang: {
    type: String,
    default: 'he'
  }
});

const currentUser = ref(null);
const isOwner = ref(false);

const likesCount = ref(0);
const isLiked = ref(false);
const isLiking = ref(false);

const comments = ref([]);
const newCommentText = ref('');
const isSubmittingComment = ref(false);

const addedToCurationMsg = ref('');
const showCurationMenu = ref(false);

let unsubAuth = null;
let unsubLikes = null;
let unsubComments = null;

const initListeners = (photoId) => {
  if (unsubLikes) unsubLikes();
  if (unsubComments) unsubComments();

  if (!photoId) return;

  unsubLikes = subscribeToPhotoLikes(photoId, (data) => {
    likesCount.value = data.count || 0;
    if (currentUser.value) {
      isLiked.value = Boolean(data.liked_by?.[currentUser.value.uid]);
    } else {
      isLiked.value = false;
    }
  });

  unsubComments = subscribeToPhotoComments(photoId, (items) => {
    comments.value = items;
  });
};

onMounted(() => {
  unsubAuth = subscribeToAuth((user) => {
    currentUser.value = user;
    isOwner.value = isUserOwner(user);
    if (props.photo?.id) {
      initListeners(props.photo.id);
    }
  });

  if (props.photo?.id) {
    initListeners(props.photo.id);
  }
});

watch(() => props.photo?.id, (newId) => {
  if (newId) {
    initListeners(newId);
  }
});

onUnmounted(() => {
  if (unsubAuth) unsubAuth();
  if (unsubLikes) unsubLikes();
  if (unsubComments) unsubComments();
});

const handleLikeClick = async () => {
  if (!currentUser.value) {
    try {
      await loginWithGoogle();
    } catch (e) {
      return;
    }
  }

  if (isLiking.value) return;
  isLiking.value = true;
  try {
    const res = await togglePhotoLike(props.photo.id, currentUser.value);
    isLiked.value = res.isLiked;
    likesCount.value = res.count;
  } catch (err) {
    console.error('Like error:', err);
  } finally {
    isLiking.value = false;
  }
};

const handleSendComment = async () => {
  if (!currentUser.value) {
    try {
      await loginWithGoogle();
    } catch (e) {
      return;
    }
  }

  const text = newCommentText.value.trim();
  if (!text || isSubmittingComment.value) return;

  isSubmittingComment.value = true;
  try {
    await addPhotoComment(props.photo.id, currentUser.value, text);
    newCommentText.value = '';
  } catch (err) {
    console.error('Comment error:', err);
  } finally {
    isSubmittingComment.value = false;
  }
};

const handleDeleteComment = async (commentId) => {
  if (!currentUser.value) return;
  try {
    await deletePhotoComment(commentId, currentUser.value);
  } catch (err) {
    console.error('Delete comment error:', err);
  }
};

const handleAddToCuration = async (area, status) => {
  showCurationMenu.value = false;
  try {
    await addPhotoToCuration(props.photo, area, status);
    addedToCurationMsg.value = props.currentLang === 'en' ? 'Added to curation!' : 'נוסף למערכת התערוכה!';
    setTimeout(() => { addedToCurationMsg.value = ''; }, 3000);
  } catch (err) {
    console.error('Add to curation error:', err);
  }
};
</script>

<template>
  <div class="space-y-4 pt-3 border-t border-slate-800/80">
    <!-- Action Bar: Likes + Add to Curation -->
    <div class="flex items-center justify-between gap-2">
      <!-- Like Button -->
      <button
        type="button"
        @click="handleLikeClick"
        :disabled="isLiking"
        class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold transition cursor-pointer border shadow-sm"
        :class="isLiked 
          ? 'bg-rose-500/20 text-rose-300 border-rose-500/50 hover:bg-rose-500/30' 
          : 'bg-slate-950/60 text-slate-300 border-slate-700/80 hover:text-rose-400 hover:border-rose-500/50 hover:bg-slate-900'"
      >
        <span class="text-sm transition-transform active:scale-125" :class="{ 'scale-110': isLiked }">
          {{ isLiked ? '❤️' : '🤍' }}
        </span>
        <span>{{ likesCount }}</span>
        <span class="text-[11px] text-slate-400 font-normal">
          {{ currentLang === 'en' ? (likesCount === 1 ? 'Like' : 'Likes') : (likesCount === 1 ? 'לייק' : 'לייקים') }}
        </span>
      </button>

      <!-- Add to Curation (Visible to logged in users or owner) -->
      <div v-if="currentUser" class="relative">
        <button
          type="button"
          @click="showCurationMenu = !showCurationMenu"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-indigo-950/50 text-indigo-300 border border-indigo-700/60 hover:bg-indigo-900/60 hover:border-indigo-500 transition cursor-pointer"
          :title="currentLang === 'en' ? 'Propose this photo for exhibition or wall' : 'הצע תמונה זו לתערוכה או לקיר תמונות'"
        >
          <span>🎨</span>
          <span>{{ currentLang === 'en' ? 'Curate' : 'הצע לתערוכה' }}</span>
        </button>

        <!-- Dropdown Menu -->
        <div
          v-if="showCurationMenu"
          class="absolute bottom-full mb-2 left-0 sm:right-0 w-52 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-1 z-40 text-xs"
        >
          <button
            type="button"
            @click="handleAddToCuration('exhibition', 'pool')"
            class="w-full text-right px-3 py-2 rounded-lg hover:bg-slate-800 text-slate-200 flex items-center gap-2 cursor-pointer"
          >
            <span>🖼️</span>
            <span>{{ currentLang === 'en' ? 'Add to Exhibition pool' : 'הוסף למאגר תערוכה' }}</span>
          </button>
          <button
            type="button"
            @click="handleAddToCuration('wall', 'pool')"
            class="w-full text-right px-3 py-2 rounded-lg hover:bg-slate-800 text-slate-200 flex items-center gap-2 cursor-pointer"
          >
            <span>🧱</span>
            <span>{{ currentLang === 'en' ? 'Add to Photo Wall' : 'הוסף לקיר תמונות' }}</span>
          </button>
          <button
            v-if="isOwner"
            type="button"
            @click="handleAddToCuration('exhibition', 'sure')"
            class="w-full text-right px-3 py-2 rounded-lg hover:bg-amber-950/40 text-amber-300 flex items-center gap-2 cursor-pointer border-t border-slate-800"
          >
            <span>🌟</span>
            <span>{{ currentLang === 'en' ? 'Mark as Locked-in (Exhibition)' : 'סמן כמועמדת בטוחה לתערוכה' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Feedback toast -->
    <div v-if="addedToCurationMsg" class="text-xs text-emerald-400 bg-emerald-950/50 border border-emerald-500/40 px-3 py-1.5 rounded-lg text-center animate-fade-in">
      ✓ {{ addedToCurationMsg }}
    </div>

    <!-- Comments Section -->
    <div class="space-y-2.5">
      <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
        <span>💬 {{ currentLang === 'en' ? 'Comments' : 'תגובות' }} ({{ comments.length }})</span>
      </h4>

      <!-- Comments List -->
      <div v-if="comments.length > 0" class="space-y-2 max-h-48 overflow-y-auto pr-1">
        <div
          v-for="c in comments"
          :key="c.id"
          class="bg-slate-950/60 border border-slate-800/80 rounded-xl p-2.5 space-y-1 text-xs"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <img
                v-if="c.user_photo"
                :src="c.user_photo"
                :alt="c.user_name"
                class="w-5 h-5 rounded-full object-cover border border-slate-700"
                referrerpolicy="no-referrer"
              />
              <span v-else class="w-5 h-5 rounded-full bg-sky-700 text-white text-[10px] flex items-center justify-center font-bold">
                {{ (c.user_name || 'U')[0].toUpperCase() }}
              </span>
              <span class="font-semibold text-slate-200">{{ c.user_name }}</span>
            </div>
            
            <button
              v-if="currentUser && (currentUser.uid === c.user_id || isOwner)"
              type="button"
              @click="handleDeleteComment(c.id)"
              class="text-slate-500 hover:text-rose-400 text-xs px-1 cursor-pointer"
              :title="currentLang === 'en' ? 'Delete comment' : 'מחק תגובה'"
            >
              ✕
            </button>
          </div>
          <p class="text-slate-300 leading-relaxed font-normal whitespace-pre-wrap">{{ c.text }}</p>
        </div>
      </div>

      <div v-else class="text-center py-3 text-xs text-slate-500 italic">
        {{ currentLang === 'en' ? 'No comments yet. Be the first to comment!' : 'אין עדיין תגובות. היה הראשון להגיב!' }}
      </div>

      <!-- Add Comment Input -->
      <div class="flex items-center gap-2 pt-1">
        <input
          v-model="newCommentText"
          type="text"
          :placeholder="currentUser 
            ? (currentLang === 'en' ? 'Write a comment...' : 'הוסף תגובה על התמונה...')
            : (currentLang === 'en' ? 'Sign in with Google to comment' : 'התחבר עם גוגל כדי להגיב')"
          class="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition"
          @keydown.enter.prevent="handleSendComment"
        />
        <button
          type="button"
          @click="handleSendComment"
          :disabled="isSubmittingComment || !newCommentText.trim()"
          class="px-3 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-medium transition cursor-pointer shadow-sm"
        >
          {{ currentLang === 'en' ? 'Post' : 'שלח' }}
        </button>
      </div>
    </div>
  </div>
</template>
