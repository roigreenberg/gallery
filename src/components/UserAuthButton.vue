<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { auth, subscribeToAuth, loginWithGoogle, logoutUser, isUserOwner } from '../utils/firebase.js';
import PhotoUploaderModal from './PhotoUploaderModal.vue';

const props = defineProps({
  lang: {
    type: String,
    default: 'he'
  }
});

const currentUser = ref(null);
const isOwner = ref(false);
const isLoading = ref(true);
const isMenuOpen = ref(false);
const showUploadModal = ref(false);
const errorMsg = ref('');

const curationUrl = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/curation/`;

let unsubscribeAuth = null;

onMounted(() => {
  unsubscribeAuth = subscribeToAuth((user) => {
    currentUser.value = user;
    isOwner.value = isUserOwner(user);
    isLoading.value = false;
  });

  const handleClickOutside = (e) => {
    if (!e.target.closest('#user-auth-menu-container')) {
      isMenuOpen.value = false;
    }
  };
  document.addEventListener('click', handleClickOutside);
  onUnmounted(() => {
    document.removeEventListener('click', handleClickOutside);
    if (unsubscribeAuth) unsubscribeAuth();
  });
});

const handleLogin = async () => {
  errorMsg.value = '';
  isLoading.value = true;
  try {
    await loginWithGoogle();
  } catch (err) {
    console.error('Login error:', err);
    errorMsg.value = props.lang === 'he' ? 'ההתחברות בוטלה או נכשלה' : 'Sign in failed or cancelled';
    setTimeout(() => { errorMsg.value = ''; }, 4000);
  } finally {
    isLoading.value = false;
  }
};

const handleLogout = async () => {
  isMenuOpen.value = false;
  await logoutUser();
};
</script>

<template>
  <div id="user-auth-menu-container" class="relative inline-block text-right">
    <!-- Logged Out State -->
    <button
      v-if="!currentUser && !isLoading"
      type="button"
      @click="handleLogin"
      class="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium bg-slate-900 border border-slate-700/80 text-slate-200 hover:text-white hover:border-sky-500 hover:bg-slate-800 transition cursor-pointer shadow-sm shrink-0"
      :title="lang === 'he' ? 'התחבר עם חשבון Google כדי לתת לייקים, להגיב ולהצביע לתערוכה' : 'Sign in with Google to like, comment and curate'"
    >
      <!-- Google 'G' Icon -->
      <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
      </svg>
      <span class="hidden xs:inline sm:inline">{{ lang === 'he' ? 'התחברות' : 'Sign In' }}</span>
    </button>

    <!-- Loading State -->
    <div
      v-else-if="isLoading"
      class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-slate-400 bg-slate-900 border border-slate-800 shrink-0"
    >
      <span class="w-3 h-3 rounded-full border-2 border-sky-400 border-t-transparent animate-spin"></span>
    </div>

    <!-- Logged In State -->
    <div v-else class="flex items-center gap-1 sm:gap-2 shrink-0">
      <button
        type="button"
        @click="isMenuOpen = !isMenuOpen"
        class="inline-flex items-center gap-1.5 sm:gap-2 p-1 sm:px-2.5 sm:py-1 rounded-lg text-xs sm:text-sm font-medium bg-slate-900/90 border border-slate-700/80 hover:border-slate-500 hover:bg-slate-800/90 text-slate-200 transition cursor-pointer shrink-0"
        :aria-expanded="isMenuOpen"
      >
        <img
          v-if="currentUser.photoURL"
          :src="currentUser.photoURL"
          :alt="currentUser.displayName || 'User'"
          class="w-6 h-6 rounded-full border border-sky-400/40 object-cover shrink-0"
          referrerpolicy="no-referrer"
        />
        <div v-else class="w-6 h-6 rounded-full bg-sky-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
          {{ (currentUser.displayName || currentUser.email || 'U')[0].toUpperCase() }}
        </div>

        <span class="hidden md:inline max-w-[120px] truncate font-medium text-xs">
          {{ currentUser.displayName || currentUser.email.split('@')[0] }}
        </span>

        <span v-if="isOwner" class="hidden sm:inline-block px-1.5 py-0.2 text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded font-semibold shrink-0">
          {{ lang === 'he' ? 'בעלים' : 'Owner' }}
        </span>
        <span v-if="isOwner" class="sm:hidden text-xs shrink-0" title="בעלים">👑</span>

        <svg class="w-3 h-3 sm:w-3.5 sm:h-3.5 text-slate-400 transition-transform shrink-0" :class="{ 'rotate-180': isMenuOpen }" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
        </svg>
      </button>

      <!-- Dropdown Menu -->
      <transition
        enter-active-class="transition duration-100 ease-out"
        enter-from-class="transform scale-95 opacity-0"
        enter-to-class="transform scale-100 opacity-100"
        leave-active-class="transition duration-75 ease-in"
        leave-from-class="transform scale-100 opacity-100"
        leave-to-class="transform scale-95 opacity-0"
      >
        <div
          v-if="isMenuOpen"
          class="absolute left-0 sm:right-0 mt-2 w-56 rounded-xl bg-slate-900 border border-slate-700/80 shadow-2xl py-1.5 z-50 text-xs backdrop-blur-xl"
        >
          <div class="px-3.5 py-2 border-b border-slate-800">
            <p class="font-semibold text-slate-200 truncate">{{ currentUser.displayName }}</p>
            <p class="text-slate-400 text-[11px] truncate">{{ currentUser.email }}</p>
          </div>

          <!-- Secret Curation Board Link (Available to logged in users) -->
          <a
            :href="curationUrl"
            class="flex items-center gap-2.5 px-3.5 py-2 text-sky-400 hover:bg-slate-800/80 hover:text-sky-300 transition"
            @click="isMenuOpen = false"
          >
            <span>🎨</span>
            <div class="flex-1 text-right">
              <span class="font-medium">{{ lang === 'he' ? 'חדר אוצרות לתערוכה' : 'Exhibition Curation' }}</span>
              <span class="block text-[10px] text-slate-400">{{ lang === 'he' ? 'בחירת תמונות ודירוג' : 'Candidate voting' }}</span>
            </div>
          </a>

          <!-- Owner Photo Upload Studio Button -->
          <button
            v-if="isOwner"
            type="button"
            @click="showUploadModal = true; isMenuOpen = false"
            class="w-full flex items-center gap-2.5 px-3.5 py-2 text-amber-300 hover:bg-amber-950/30 transition text-right cursor-pointer"
          >
            <span>📸</span>
            <div class="flex-1 text-right">
              <span class="font-medium">{{ lang === 'he' ? 'העלאת תמונות (Studio)' : 'Upload Photos (Studio)' }}</span>
              <span class="block text-[10px] text-amber-400/70">{{ lang === 'he' ? 'חילוץ EXIF ו-AI אוטומטי' : 'Auto EXIF & AI' }}</span>
            </div>
          </button>

          <!-- Logout Button -->
          <button
            type="button"
            @click="handleLogout"
            class="w-full flex items-center gap-2.5 px-3.5 py-2 text-rose-400 hover:bg-rose-950/20 hover:text-rose-300 transition text-right cursor-pointer border-t border-slate-800/60"
          >
            <span>🚪</span>
            <span>{{ lang === 'he' ? 'התנתקות' : 'Sign Out' }}</span>
          </button>
        </div>
      </transition>
    </div>

    <!-- Error Toast -->
    <div
      v-if="errorMsg"
      class="absolute top-full mt-1 right-0 bg-rose-900/90 border border-rose-600 text-rose-100 text-[11px] px-2.5 py-1 rounded shadow-lg whitespace-nowrap z-50"
    >
      {{ errorMsg }}
    </div>

    <!-- Owner Photo Upload Modal -->
    <PhotoUploaderModal
      v-if="showUploadModal && currentUser && isOwner"
      :current-user="currentUser"
      :current-lang="lang"
      @close="showUploadModal = false"
    />
  </div>
</template>
