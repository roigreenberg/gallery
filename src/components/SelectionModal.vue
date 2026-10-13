<script setup>
import { ref, computed } from 'vue';
import { X, Copy, Check, Trash2, ExternalLink, MessageCircle } from 'lucide-vue-next';

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  },
  selectedPhotos: {
    type: Array,
    required: true
  }
});

const emit = defineEmits(['close', 'remove', 'clear']);

const copied = ref(false);

const getPhotoShareUrl = (photoId) => {
  if (typeof window === 'undefined') return '';
  const url = new URL(window.location.href);
  url.search = `?photo=${encodeURIComponent(photoId)}`;
  url.hash = '';
  return url.toString();
};

// Generate formatted export text with direct photo URLs for WhatsApp
const formattedText = computed(() => {
  if (props.selectedPhotos.length === 0) return '';
  const lines = ['בחרתי את התמונות הבאות:'];
  props.selectedPhotos.forEach(p => {
    const link = getPhotoShareUrl(p.id);
    if (link) {
      lines.push(`• ${p.title}\n  ${link}`);
    } else {
      lines.push(`• ${p.title} (מזהה: ${p.id})`);
    }
  });
  return lines.join('\n');
});

// Copy to clipboard
const copyToClipboard = async () => {
  if (!formattedText.value) return;
  try {
    await navigator.clipboard.writeText(formattedText.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 3000);
  } catch (err) {
    // Fallback if clipboard API is restricted
    const textArea = document.createElement('textarea');
    textArea.value = formattedText.value;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 3000);
  }
};

// WhatsApp direct link
const openWhatsApp = () => {
  if (!formattedText.value) return;
  const url = `https://api.whatsapp.com/send?text=${encodeURIComponent(formattedText.value)}`;
  window.open(url, '_blank');
};
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
    role="dialog"
    aria-modal="true"
  >
    <!-- Backdrop Blur Overlay -->
    <div
      class="fixed inset-0 bg-slate-950/80 backdrop-blur-md transition-opacity"
      @click="emit('close')"
    ></div>

    <!-- Modal Card Content -->
    <div
      class="relative w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[88vh] z-10 animate-scale-in text-right"
      dir="rtl"
    >
      <!-- Header -->
      <div class="px-6 py-4 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between shrink-0">
        <div class="flex items-center gap-2.5">
          <span class="text-xl">📋</span>
          <div>
            <h3 class="text-base font-bold text-white">רשימת תמונות שבחרת</h3>
            <p class="text-xs text-slate-400">
              {{ selectedPhotos.length }} תמונות נבחרו
            </p>
          </div>
        </div>

        <button
          type="button"
          @click="emit('close')"
          class="w-8 h-8 rounded-full bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition cursor-pointer"
          aria-label="סגור חלון"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Explanation banner -->
      <div class="px-6 py-3 bg-sky-950/30 border-b border-sky-800/30 text-xs text-sky-200/90 leading-relaxed">
        💡 <strong>איך זה עובד?</strong> לאחר שסימנת את התמונות שאהבת, לחץ על <strong>העתק רשימה</strong> והדבק אותה בהודעה לרועי בוואטסאפ לבירור, הדפסה או רכישה.
      </div>

      <!-- Modal Body (Scrollable) -->
      <div class="p-6 overflow-y-auto space-y-5 flex-1 scrollbar-thin">
        
        <!-- Empty State -->
        <div
          v-if="selectedPhotos.length === 0"
          class="text-center py-10 px-4 space-y-3"
        >
          <div class="w-14 h-14 mx-auto rounded-full bg-slate-800 flex items-center justify-center text-slate-500 text-2xl">
            🖼️
          </div>
          <h4 class="text-sm font-semibold text-slate-300">עדיין לא בחרת תמונות</h4>
          <p class="text-xs text-slate-400 max-w-xs mx-auto">
            לחץ על כפתור הסימון (+) בפינת כל תמונה בגלריה כדי להוסיף אותה לרשימה שלך.
          </p>
        </div>

        <!-- Selected Photos List -->
        <div v-else class="space-y-4">
          <!-- Items List -->
          <div class="space-y-2 max-h-56 overflow-y-auto pr-1">
            <div
              v-for="photo in selectedPhotos"
              :key="photo.id"
              class="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700 transition"
            >
              <div class="flex items-center gap-3 min-w-0">
                <img
                  :src="photo.thumbnail"
                  :alt="photo.title"
                  class="w-11 h-11 rounded-lg object-cover bg-slate-900 border border-slate-700/50 shrink-0"
                />
                <div class="min-w-0">
                  <h5 class="text-xs font-semibold text-white truncate">{{ photo.title }}</h5>
                  <p class="text-[11px] text-slate-400 truncate">{{ photo.species_he || photo.category }}</p>
                </div>
              </div>

              <button
                type="button"
                @click="emit('remove', photo.id)"
                class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/30 transition cursor-pointer shrink-0"
                title="הסר מרשימת הבחירה"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Text Preview Box -->
          <div class="space-y-1.5">
            <label class="text-xs font-medium text-slate-400">תצוגה מקדימה של ההודעה שתועתק:</label>
            <pre class="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap font-sans max-h-36 overflow-y-auto leading-relaxed select-all">{{ formattedText }}</pre>
          </div>
        </div>

      </div>

      <!-- Footer Actions -->
      <div class="px-6 py-4 border-t border-slate-800 bg-slate-950/70 flex flex-wrap items-center justify-between gap-3 shrink-0">
        
        <!-- Clear Button -->
        <button
          v-if="selectedPhotos.length > 0"
          type="button"
          @click="emit('clear')"
          class="text-xs text-slate-400 hover:text-rose-400 transition cursor-pointer flex items-center gap-1"
        >
          <Trash2 class="w-3.5 h-3.5" />
          <span>נקה בחירה</span>
        </button>
        <div v-else></div>

        <!-- Copy & WhatsApp Buttons -->
        <div class="flex items-center gap-2">
          <button
            v-if="selectedPhotos.length > 0"
            type="button"
            @click="openWhatsApp"
            class="px-3.5 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-600/40 text-xs font-bold transition flex items-center gap-1.5 cursor-pointer"
            title="פתח שיחה בוואטסאפ"
          >
            <MessageCircle class="w-3.5 h-3.5" />
            <span>וואטסאפ</span>
          </button>

          <button
            :disabled="selectedPhotos.length === 0"
            type="button"
            @click="copyToClipboard"
            class="px-5 py-2.5 rounded-xl font-bold text-xs transition flex items-center gap-2 cursor-pointer shadow-md disabled:opacity-40 disabled:cursor-not-allowed"
            :class="copied ? 'bg-emerald-500 text-slate-950' : 'bg-sky-500 hover:bg-sky-400 text-slate-950'"
          >
            <Check v-if="copied" class="w-4 h-4" />
            <Copy v-else class="w-4 h-4" />
            <span>{{ copied ? '✓ הועתק בהצלחה!' : 'העתק רשימה' }}</span>
          </button>
        </div>

      </div>

    </div>
  </div>
</template>
