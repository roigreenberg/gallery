import os
import json
import http.server
import socketserver
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from google import genai

load_dotenv()

PORT = 5050
DATA_FILE = os.path.join(os.path.dirname(__file__), "src", "data", "photos.json")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

# Initialize Gemini Client if API key is provided
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

def load_photos():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_photos(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def refine_batch_with_gemini(items_batch, model_name="gemini-3.1-flash-lite"):
    """
    Process a batch of items (up to 10 photos + instructions) in a single Gemini call.
    items_batch: list of {"photo_id": id, "context": {...}, "instruction": "..."}
    """
    if not client:
        raise ValueError("GEMINI_API_KEY is not configured in .env file.")

    prompt = f"""
You are an expert natural science, wildlife, and astronomy editor for a high-end photography portfolio.
You are given a batch of photograph metadata items along with specific revision instructions from the photographer.

Input items batch:
{json.dumps(items_batch, ensure_ascii=False, indent=2)}

For EACH item in the batch, generate an updated metadata object according to the photographer's instructions.
Return ONLY a valid JSON array of objects, where each object has:
[
  {{
    "photo_id": "<exact matching photo_id>",
    "title": "כותרת קצרה וקולעת",
    "species_hebrew": "שם המין בעברית",
    "species_latin": "Scientific Latin name",
    "category": "wildlife/landscape/astrophotography/macro",
    "behavior": ["התנהגות 1", "התנהגות 2"],
    "tags": ["תגית 1", "תגית 2", "תגית 3"],
    "description": "תיאור מדויק ופואטי במשפט אחד"
  }}
]
Ensure the response is STRICTLY valid JSON without extra text or markdown formatting outside the JSON array.
"""

    models_to_try = [model_name, "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    # Deduplicate while preserving order
    seen = set()
    unique_models = [m for m in models_to_try if not (m in seen or seen.add(m))]

    response = None
    last_err = None

    for m in unique_models:
        try:
            response = client.models.generate_content(
                model=m,
                contents=prompt,
            )
            if response and response.text:
                break
        except Exception as e:
            last_err = e
            continue

    if not response or not response.text:
        raise last_err or ValueError("Failed to get response from Gemini")

    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    return json.loads(text)

HTML_PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl" class="h-full">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>כלי עריכת תמונות ו-Batch AI | רועי גרינברג</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Assistant', sans-serif; background-color: #090a0f; color: #f1f5f9; }
    .scrollbar-thin::-webkit-scrollbar { width: 6px; }
    .scrollbar-thin::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
    .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #334155; }
  </style>
</head>
<body class="h-full flex flex-col overflow-hidden">

  <!-- Header -->
  <header class="bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-6 py-3.5 flex items-center justify-between shrink-0 z-30">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-white shadow-md">
        RG
      </div>
      <div>
        <h1 class="text-base font-bold text-white">כלי עריכת תוכן תמונות (Admin Studio)</h1>
        <p class="text-xs text-slate-400">עריכה ישירה ידנית או כתיבת הערות ושליחה מרוכזת (Batch) ל-Gemini 3.1</p>
      </div>
    </div>
    
    <!-- Top Actions & Pending Queue Badge -->
    <div class="flex items-center gap-3">
      <!-- Pending Queue Pill & Send Button -->
      <div id="batchPillContainer" class="hidden items-center gap-2 bg-amber-950/50 border border-amber-600/60 px-3 py-1.5 rounded-xl">
        <span class="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
        <span class="text-xs font-semibold text-amber-300">
          <strong id="pendingQueueCount">0</strong> הערות ממתינות לשליחה
        </span>
        <button
          onclick="processPendingBatch()"
          id="btnSendBatchTop"
          class="text-xs bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-3 py-1 rounded-lg transition shadow-md cursor-pointer ml-1"
        >
          🚀 שלח את כולם ל-AI עכשיו
        </button>
      </div>

      <a href="http://localhost:4321/gallery/" target="_blank" class="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 transition">
        <span>צפה באתר החי ↗</span>
      </a>
      <span id="saveStatus" class="text-xs font-semibold text-emerald-400 hidden">✓ השינויים נשמרו</span>
    </div>
  </header>

  <!-- Main 2-column layout -->
  <main class="flex-1 flex min-h-0 overflow-hidden">
    
    <!-- Left list: Photos Sidebar -->
    <aside class="w-80 md:w-96 border-l border-slate-800/80 bg-slate-950/80 flex flex-col shrink-0">
      
      <!-- Sticky Sidebar Controls -->
      <div class="p-3 border-b border-slate-800/80 bg-slate-950/90 space-y-2.5 shrink-0">
        <!-- Search filter -->
        <input
          type="text"
          id="filterInput"
          placeholder="סינון מהיר לפי שם, מין, או קטגוריה..."
          class="w-full text-xs px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
        />

        <!-- Sort selector -->
        <div class="flex items-center justify-between text-xs gap-2">
          <span class="text-slate-400 shrink-0">מיון תמונות:</span>
          <select
            id="sortSelect"
            onchange="handleSortChange()"
            class="flex-1 text-xs px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-200 focus:outline-none focus:border-sky-500 cursor-pointer"
          >
            <option value="pending_first">📝 הערות ממתינות בראש (Pending Queue)</option>
            <option value="featured_first">⭐ תמונות נבחרות תחילה (Featured)</option>
            <option value="featured_only">⭐ תמונות נבחרות בלבד</option>
            <option value="recent_edited">⚡ נערך לאחרונה (חדש לישן)</option>
            <option value="default">📅 תאריך מקורי / צילום</option>
            <option value="title_asc">🔤 שם התמונה (א-ת)</option>
            <option value="category">🏷️ לפי קטגוריה</option>
          </select>
        </div>

        <!-- Counter info -->
        <div class="flex items-center justify-between text-[11px] text-slate-500 px-1 pt-0.5">
          <span id="photoCountLabel">טוען תמונות...</span>
          <span id="editedCountBadge" class="text-sky-400"></span>
        </div>
      </div>

      <!-- Scrollable List of Photos -->
      <div id="photosList" class="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2"></div>
    </aside>

    <!-- Right area: Editor Panel -->
    <section class="flex-1 overflow-y-auto scrollbar-thin p-6 md:p-8 bg-[#090a0f]">
      <div id="editorEmptyState" class="h-full flex items-center justify-center text-slate-500 text-sm">
        בחר תמונה מהרשימה בצד ימין כדי לערוך את תוכנה
      </div>

      <div id="editorContent" class="max-w-4xl mx-auto space-y-6 hidden">
        
        <!-- Photo Preview Card -->
        <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 flex flex-col md:flex-row gap-5 items-start">
          <img id="editThumbnail" src="" class="w-full md:w-56 h-36 object-cover rounded-xl border border-slate-700 shadow-md shrink-0 bg-slate-950" />
          <div class="space-y-2 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span id="editCategoryBadge" class="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-sky-950 text-sky-300 border border-sky-800"></span>
              <span id="editIdBadge" class="text-xs font-mono text-slate-500"></span>
              <span id="editLastEditedBadge" class="text-[11px] font-medium text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded-full hidden"></span>
              <span id="editPendingBadge" class="text-[11px] font-medium text-amber-300 bg-amber-950/80 border border-amber-600/70 px-2.5 py-0.5 rounded-full hidden">📝 הערה ממתינה לשליחה</span>
              <button
                id="btnToggleFeatured"
                type="button"
                onclick="toggleFeatured()"
                class="text-xs font-medium px-3 py-1 rounded-full border border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700 transition flex items-center gap-1.5 cursor-pointer shadow-sm"
              >
                <span id="featuredStarIcon">☆</span>
                <span id="featuredLabel">סמן כנבחרת</span>
              </button>
            </div>
            <h2 id="editHeaderTitle" class="text-xl font-bold text-white"></h2>
            <p id="editSpeciesHeader" class="text-sm text-sky-400"></p>
            <p id="editLocationHeader" class="text-xs text-slate-400"></p>
          </div>
        </div>

        <!-- AI Note & Batch Assistant Block -->
        <div class="bg-gradient-to-r from-sky-950/50 via-indigo-950/40 to-purple-950/30 border border-sky-700/50 rounded-2xl p-5 shadow-lg space-y-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-base">✨</span>
              <h3 class="text-sm font-bold text-sky-200">הנחיות ותיקון חכם עם AI (Gemini 3.1)</h3>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-400">מודל:</span>
              <span class="px-2 py-0.5 rounded bg-sky-900/60 text-sky-300 font-mono text-[11px]">Gemini 3.1</span>
            </div>
          </div>
          <p class="text-xs text-slate-300">
            כתוב הערה או הנחיה לתמונה זו (למשל: <em>"שנה את המין לדיה שחורה"</em>, <em>"קצר את התיאור ותדגיש את התאורה"</em>).  
            תוכל לשמור את ההערה בתור ולעבור לתמונות נוספות, או לשלוח אותה מיידית בנפרד.
          </p>

          <div class="space-y-3">
            <textarea
              id="aiInstructionInput"
              rows="2"
              placeholder="כתוב כאן את ההערה או ההנחיה לתמונה זו..."
              class="w-full text-sm px-4 py-2.5 rounded-xl bg-slate-900/90 border border-sky-800/80 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500"
            ></textarea>
            
            <div class="flex flex-wrap items-center justify-between gap-3">
              <!-- Left: Queue Action -->
              <div class="flex items-center gap-2">
                <button
                  id="btnQueueNote"
                  onclick="handleQueueNote()"
                  class="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs sm:text-sm flex items-center gap-1.5 transition shadow-md cursor-pointer"
                >
                  <span>📌 שמור הערה בתור (לאיסוף מרוכז)</span>
                </button>
                <button
                  id="btnRemoveQueueNote"
                  onclick="handleRemoveQueueNote()"
                  class="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 text-xs transition cursor-pointer hidden"
                >
                  בטל הערה
                </button>
              </div>

              <!-- Right: Single Instant Send & Direct Batch Send -->
              <div class="flex items-center gap-2">
                <button
                  id="btnRunAi"
                  onclick="handleSingleAiRefine()"
                  class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs sm:text-sm flex items-center gap-1.5 transition border border-slate-700 cursor-pointer"
                >
                  <span>⚡ שלח תמונה זו בלבד</span>
                </button>
                <button
                  onclick="processPendingBatch()"
                  class="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold text-xs sm:text-sm flex items-center gap-1.5 transition shadow-lg shadow-amber-500/25 cursor-pointer"
                >
                  <span>🚀 שלח את כל ההערות עכשיו</span>
                </button>
              </div>
            </div>
          </div>

          <div id="aiLoadingIndicator" class="text-xs text-sky-400 hidden flex items-center gap-2 animate-pulse pt-1">
            <span id="aiLoadingText">מבצע עיבוד עם Gemini 3.1... אנא המתן</span>
          </div>
        </div>

        <!-- Direct Manual Editing Form -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 class="text-sm font-bold text-slate-200">עריכה ישירה של השדות</h3>
            <span class="text-[11px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">עריכה ידנית</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- Title -->
            <div class="md:col-span-2">
              <label class="block text-xs font-medium text-slate-400 mb-1">כותרת התמונה</label>
              <input type="text" id="formTitle" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500" />
            </div>

            <!-- Species HE -->
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">שם המין (עברית)</label>
              <input type="text" id="formSpeciesHe" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500" />
            </div>

            <!-- Species LA -->
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">שם מדעי (לטינית)</label>
              <input type="text" id="formSpeciesLa" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500" />
            </div>

            <!-- Category -->
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">קטגוריה</label>
              <select id="formCategory" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500">
                <option value="wildlife">wildlife (טבע וציפורים)</option>
                <option value="landscape">landscape (נוף)</option>
                <option value="astrophotography">astrophotography (אסטרו)</option>
                <option value="macro">macro (מאקרו)</option>
              </select>
            </div>

            <!-- Tags -->
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">תגיות (מופרדות בפסיקים)</label>
              <input type="text" id="formTags" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500" />
            </div>

            <!-- Description -->
            <div class="md:col-span-2">
              <label class="block text-xs font-medium text-slate-400 mb-1">תיאור התמונה</label>
              <textarea id="formDescription" rows="3" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500"></textarea>
            </div>

            <!-- Camera -->
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">גוף מצלמה</label>
              <input type="text" id="formCamera" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500" />
            </div>

            <!-- Lens -->
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">עדשה</label>
              <input type="text" id="formLens" class="w-full text-sm px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-sky-500" />
            </div>

            <!-- Exposure fields -->
            <div class="grid grid-cols-3 gap-2 md:col-span-2">
              <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">מוקד</label>
                <input type="text" id="formFocal" class="w-full text-xs px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white" />
              </div>
              <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">צמצם</label>
                <input type="text" id="formAperture" class="w-full text-xs px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white" />
              </div>
              <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">מהירות</label>
                <input type="text" id="formShutter" class="w-full text-xs px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white" />
              </div>
            </div>
          </div>

          <!-- Save Button -->
          <div class="pt-4 flex items-center justify-end gap-3 border-t border-slate-800">
            <button
              onclick="saveDirectForm()"
              class="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white font-medium text-sm flex items-center gap-1.5 transition shadow-lg shadow-emerald-500/20 cursor-pointer"
            >
              <span>שמור שינויים ב-JSON</span>
            </button>
          </div>
        </div>

      </div>
    </section>
  </main>

  <!-- Batch Progress Modal Overlay -->
  <div id="batchProgressModal" class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md hidden items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl text-center space-y-4">
      <div class="w-14 h-14 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-2xl">
        ⚡
      </div>
      <h3 class="text-lg font-bold text-white">עיבוד מרוכז ב-Gemini 3.1</h3>
      <p id="batchModalText" class="text-sm text-amber-300 font-medium">מתחיל שליחה מרוכזת...</p>
      
      <!-- Progress Bar -->
      <div class="w-full bg-slate-950 rounded-full h-3 overflow-hidden border border-slate-800">
        <div id="batchModalProgressBar" class="bg-gradient-to-r from-amber-500 to-orange-500 h-full w-0 transition-all duration-300 rounded-full"></div>
      </div>
      
      <p id="batchModalSubtext" class="text-xs text-slate-400 leading-relaxed">
        ההערות נשלחות בקבוצות של עד 10 תמונות בכל פעם.
      </p>
    </div>
  </div>

  <script>
    let photos = [];
    let currentPhotoId = null;
    let currentSort = 'pending_first';
    
    // In-memory queue of pending notes: { [photo_id]: instruction_text }
    const pendingNotes = JSON.parse(localStorage.getItem('admin_pending_notes') || '{}');

    function savePendingNotesToStorage() {
      localStorage.setItem('admin_pending_notes', JSON.stringify(pendingNotes));
      updatePendingUI();
    }

    function updatePendingUI() {
      const keys = Object.keys(pendingNotes);
      const count = keys.length;
      const countElem = document.getElementById('pendingQueueCount');
      const container = document.getElementById('batchPillContainer');

      if (countElem) countElem.innerText = count;
      if (container) {
        if (count > 0) {
          container.classList.remove('hidden');
          container.classList.add('flex');
        } else {
          container.classList.add('hidden');
          container.classList.remove('flex');
        }
      }
    }

    function getThumbUrl(photo) {
      if (!photo) return '';
      if (photo.thumb_url) return photo.thumb_url;
      const t = photo.paths?.thumbnail || photo.thumbnail;
      if (!t) return '';
      if (t.startsWith('http://') || t.startsWith('https://')) return t;
      return t.startsWith('/') ? t : '/' + t;
    }

    function getPhotoTitle(photo) {
      return photo.ai?.title || photo.title || photo.filename || 'תמונה';
    }

    function getPhotoSpecies(photo) {
      return photo.ai?.species_hebrew || photo.species_he || '';
    }

    function getPhotoCategory(photo) {
      return photo.ai?.category || photo.category || 'wildlife';
    }

    function formatTimeAgo(isoString) {
      if (!isoString) return '';
      try {
        const d = new Date(isoString);
        const now = new Date();
        const diffSec = Math.floor((now - d) / 1000);
        if (diffSec < 60) return 'לפני רגע';
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return `לפני ${diffMin} דק'`;
        const diffHours = Math.floor(diffMin / 60);
        if (diffHours < 24) return `לפני ${diffHours} שע'`;
        return d.toLocaleDateString('he-IL');
      } catch (e) {
        return '';
      }
    }

    async function loadData() {
      const countLabel = document.getElementById('photoCountLabel');
      const container = document.getElementById('photosList');
      
      try {
        if (countLabel) countLabel.innerText = 'טוען נתונים מהשרת...';
        if (container) {
          container.innerHTML = '<div class="p-4 text-center text-xs text-sky-400 animate-pulse">טוען את קטלוג התמונות...</div>';
        }

        const res = await fetch('/api/photos');
        if (!res.ok) throw new Error('שגיאה בטעינת קובץ התמונות');
        
        photos = await res.json();
        if (countLabel) countLabel.innerText = `נטענו ${photos.length} תמונות`;

        updatePendingUI();
        renderSidebar();

        if (photos.length > 0 && !currentPhotoId) {
          const sorted = getSortedPhotos();
          if (sorted.length > 0) {
            selectPhoto(sorted[0].id);
          }
        }
      } catch (err) {
        console.error(err);
        if (countLabel) countLabel.innerText = 'שגיאה בטעינה';
        if (container) {
          container.innerHTML = `<div class="p-4 text-center text-xs text-rose-400 bg-rose-950/30 rounded-xl border border-rose-800/50">שגיאה בטעינת התמונות: ${err.message}<br><button onclick="loadData()" class="mt-2 text-xs bg-slate-800 text-slate-200 px-3 py-1 rounded-lg">נסה שוב</button></div>`;
        }
      }
    }

    function handleSortChange() {
      currentSort = document.getElementById('sortSelect').value;
      renderSidebar();
    }

    function getSortedPhotos() {
      const copy = [...photos];
      if (currentSort === 'pending_first') {
        copy.sort((a, b) => {
          const aHas = Boolean(pendingNotes[a.id]);
          const bHas = Boolean(pendingNotes[b.id]);
          if (aHas && !bHas) return -1;
          if (!aHas && bHas) return 1;
          const aEdit = a.last_edited_at || '';
          const bEdit = b.last_edited_at || '';
          return bEdit.localeCompare(aEdit);
        });
      } else if (currentSort === 'featured_first') {
        copy.sort((a, b) => {
          const aF = Boolean(a.is_featured);
          const bF = Boolean(b.is_featured);
          if (aF && !bF) return -1;
          if (!aF && bF) return 1;
          const aEdit = a.last_edited_at || '';
          const bEdit = b.last_edited_at || '';
          return bEdit.localeCompare(aEdit);
        });
      } else if (currentSort === 'featured_only') {
        return copy.filter(p => Boolean(p.is_featured));
      } else if (currentSort === 'recent_edited') {
        copy.sort((a, b) => {
          const aEdit = a.last_edited_at || '';
          const bEdit = b.last_edited_at || '';
          if (aEdit && bEdit) return bEdit.localeCompare(aEdit);
          if (aEdit) return -1;
          if (bEdit) return 1;
          return (b.processed_at || '').localeCompare(a.processed_at || '');
        });
      } else if (currentSort === 'default') {
        copy.sort((a, b) => {
          const aDate = a.exif?.date_time_original || a.exif?.date || '';
          const bDate = b.exif?.date_time_original || b.exif?.date || '';
          return bDate.localeCompare(aDate);
        });
      } else if (currentSort === 'title_asc') {
        copy.sort((a, b) => getPhotoTitle(a).localeCompare(getPhotoTitle(b), 'he'));
      } else if (currentSort === 'category') {
        copy.sort((a, b) => getPhotoCategory(a).localeCompare(getPhotoCategory(b)));
      }
      return copy;
    }

    function renderSidebar() {
      const filter = document.getElementById('filterInput').value.toLowerCase();
      const container = document.getElementById('photosList');
      container.innerHTML = '';

      const sortedPhotos = getSortedPhotos();
      let displayedCount = 0;
      let editedCount = 0;
      let featuredCount = 0;

      photos.forEach(p => {
        if (p.last_edited_at) editedCount++;
        if (p.is_featured) featuredCount++;
      });

      const fragment = document.createDocumentFragment();

      sortedPhotos.forEach(p => {
        const title = getPhotoTitle(p);
        const species = getPhotoSpecies(p);
        const cat = getPhotoCategory(p);
        const match = !filter || title.toLowerCase().includes(filter) || species.toLowerCase().includes(filter) || cat.toLowerCase().includes(filter);
        if (!match) return;

        displayedCount++;
        const isSelected = p.id === currentPhotoId;
        const isEdited = Boolean(p.last_edited_at);
        const isFeatured = Boolean(p.is_featured);
        const hasPendingNote = Boolean(pendingNotes[p.id]);
        const timeLabel = formatTimeAgo(p.last_edited_at);

        const div = document.createElement('div');
        div.dataset.id = p.id;
        div.className = `p-2.5 rounded-xl border transition cursor-pointer flex items-center gap-3 ${
          isSelected
            ? 'bg-sky-950/80 border-sky-500 text-white shadow-md'
            : hasPendingNote
              ? 'bg-amber-950/40 border-amber-700/60 text-slate-200'
              : 'bg-slate-900/60 hover:bg-slate-800/80 border-slate-800/80 text-slate-300'
        }`;
        div.onclick = () => selectPhoto(p.id);

        div.innerHTML = `
          <div class="relative w-12 h-12 shrink-0">
            <img src="${getThumbUrl(p)}" class="w-12 h-12 rounded-lg object-cover border border-slate-700/50 bg-slate-950" loading="lazy" />
            ${hasPendingNote ? '<span class="absolute -top-1 -right-1 w-3 h-3 bg-amber-400 rounded-full ring-2 ring-slate-950 flex items-center justify-center text-[8px] text-slate-950 font-bold">!</span>' : isEdited ? '<span class="absolute -top-1 -right-1 w-2.5 h-2.5 bg-emerald-400 rounded-full ring-2 ring-slate-950"></span>' : ''}
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between gap-1">
              <div class="flex items-center gap-1 min-w-0">
                ${isFeatured ? '<span class="text-xs text-amber-400 font-bold shrink-0" title="תמונה נבחרת">⭐</span>' : ''}
                <h4 class="text-xs font-semibold truncate ${isSelected ? 'text-sky-300' : hasPendingNote ? 'text-amber-300' : 'text-slate-200'}">${title}</h4>
              </div>
              ${hasPendingNote ? '<span class="text-[9px] bg-amber-900/80 text-amber-200 px-1 rounded font-mono">הערה</span>' : isEdited ? `<span class="text-[10px] text-emerald-400 shrink-0 font-medium">${timeLabel}</span>` : ''}
            </div>
            <p class="text-[11px] text-slate-400 truncate">${species || '-'}</p>
            <span class="text-[10px] text-slate-500">${cat}</span>
          </div>
        `;
        fragment.appendChild(div);
      });

      container.appendChild(fragment);

      document.getElementById('photoCountLabel').innerText = `מוצגות ${displayedCount} מתוך ${photos.length}`;
      document.getElementById('editedCountBadge').innerText = `${featuredCount > 0 ? `(${featuredCount} ⭐ נבחרות)` : ''}`;
    }

    document.getElementById('filterInput').addEventListener('input', renderSidebar);

    async function toggleFeatured() {
      const photo = photos.find(p => p.id === currentPhotoId);
      if (!photo) return;
      photo.is_featured = !Boolean(photo.is_featured);
      photo.last_edited_at = new Date().toISOString();
      await persistPhoto(photo);
      renderSidebar();
      selectPhoto(currentPhotoId);
    }

    function selectPhoto(id) {
      currentPhotoId = id;
      const photo = photos.find(p => p.id === id);
      if (!photo) return;

      // Update active highlight classes directly in DOM without rebuilding all 431 items
      document.querySelectorAll('#photosList > div').forEach(el => {
        if (el.dataset.id === id) {
          el.className = 'p-2.5 rounded-xl border transition cursor-pointer flex items-center gap-3 bg-sky-950/80 border-sky-500 text-white shadow-md';
        } else {
          const hasNote = Boolean(pendingNotes[el.dataset.id]);
          el.className = `p-2.5 rounded-xl border transition cursor-pointer flex items-center gap-3 ${
            hasNote ? 'bg-amber-950/40 border-amber-700/60 text-slate-200' : 'bg-slate-900/60 hover:bg-slate-800/80 border-slate-800/80 text-slate-300'
          }`;
        }
      });

      document.getElementById('editorEmptyState').classList.add('hidden');
      document.getElementById('editorContent').classList.remove('hidden');

      const ai = photo.ai || {};
      const exif = photo.exif || {};

      // Preview card
      document.getElementById('editThumbnail').src = getThumbUrl(photo);
      document.getElementById('editCategoryBadge').innerText = getPhotoCategory(photo);
      document.getElementById('editIdBadge').innerText = photo.id;
      document.getElementById('editHeaderTitle').innerText = getPhotoTitle(photo);
      const rawDate = exif.date_time_original || '';
      const dateMatch = rawDate.match(/^(\d{4})[:\-](\d{2})[:\-](\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?/);
      const formattedExifDate = dateMatch ? (dateMatch[4] ? `${dateMatch[3]}/${dateMatch[2]}/${dateMatch[1]} ${dateMatch[4]}` : `${dateMatch[3]}/${dateMatch[2]}/${dateMatch[1]}`) : rawDate;
      document.getElementById('editLocationHeader').innerText = formattedExifDate ? `${formattedExifDate} • ${exif.camera_model || ''}` : (exif.camera_model || '');

      // Update Featured button state
      const btnFeatured = document.getElementById('btnToggleFeatured');
      const starIcon = document.getElementById('featuredStarIcon');
      const featLabel = document.getElementById('featuredLabel');
      if (btnFeatured) {
        if (photo.is_featured) {
          btnFeatured.className = 'text-xs font-semibold px-3 py-1 rounded-full border border-amber-500/70 bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 transition flex items-center gap-1.5 cursor-pointer shadow-sm';
          starIcon.innerText = '⭐';
          featLabel.innerText = 'תמונה נבחרת (לחץ לביטול)';
        } else {
          btnFeatured.className = 'text-xs font-medium px-3 py-1 rounded-full border border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700 transition flex items-center gap-1.5 cursor-pointer shadow-sm';
          starIcon.innerText = '☆';
          featLabel.innerText = 'סמן כתמונה נבחרת';
        }
      }

      const lastEditedBadge = document.getElementById('editLastEditedBadge');
      if (photo.last_edited_at) {
        lastEditedBadge.innerText = `נערך לאחרונה: ${new Date(photo.last_edited_at).toLocaleString('he-IL')}`;
        lastEditedBadge.classList.remove('hidden');
      } else {
        lastEditedBadge.classList.add('hidden');
      }

      const pendingBadge = document.getElementById('editPendingBadge');
      const btnRemoveNote = document.getElementById('btnRemoveQueueNote');
      if (pendingNotes[photo.id]) {
        pendingBadge.classList.remove('hidden');
        btnRemoveNote.classList.remove('hidden');
        document.getElementById('aiInstructionInput').value = pendingNotes[photo.id];
      } else {
        pendingBadge.classList.add('hidden');
        btnRemoveNote.classList.add('hidden');
        document.getElementById('aiInstructionInput').value = '';
      }

      // Populate direct form
      document.getElementById('formTitle').value = ai.title || photo.title || '';
      document.getElementById('formSpeciesHe').value = ai.species_hebrew || photo.species_he || '';
      document.getElementById('formSpeciesLa').value = ai.species_latin || photo.species_la || '';
      document.getElementById('formCategory').value = ai.category || photo.category || 'wildlife';
      
      const tags = ai.tags || photo.tags || [];
      document.getElementById('formTags').value = Array.isArray(tags) ? tags.join(', ') : '';
      document.getElementById('formDescription').value = ai.description || photo.description || '';
      
      document.getElementById('formCamera').value = exif.camera_model || exif.camera || '';
      document.getElementById('formLens').value = exif.lens_model || exif.lens || '';
      document.getElementById('formFocal').value = exif.focal_length || exif.focalLength || '';
      document.getElementById('formAperture').value = exif.aperture || '';
      document.getElementById('formShutter').value = exif.shutter_speed || exif.shutterSpeed || '';
    }

    function handleQueueNote() {
      const text = document.getElementById('aiInstructionInput').value.trim();
      if (!text) {
        alert('אנא הזן הערה או הנחיה לפני ההוספה לתור');
        return;
      }
      pendingNotes[currentPhotoId] = text;
      savePendingNotesToStorage();
      renderSidebar();
      selectPhoto(currentPhotoId);
    }

    function handleRemoveQueueNote() {
      delete pendingNotes[currentPhotoId];
      savePendingNotesToStorage();
      renderSidebar();
      selectPhoto(currentPhotoId);
    }

    async function handleSingleAiRefine() {
      const instruction = document.getElementById('aiInstructionInput').value.trim();
      if (!instruction) {
        alert('אנא הזן הנחיה או הערה עבור ה-AI');
        return;
      }

      const photo = photos.find(p => p.id === currentPhotoId);
      if (!photo) return;

      const btn = document.getElementById('btnRunAi');
      const loader = document.getElementById('aiLoadingIndicator');
      const loaderText = document.getElementById('aiLoadingText');
      btn.disabled = true;
      loaderText.innerText = 'מבצע עיבוד עם Gemini 3.1... אנא המתן';
      loader.classList.remove('hidden');

      try {
        const item = {
          photo_id: photo.id,
          context: {
            title: photo.ai?.title || photo.title,
            species_hebrew: photo.ai?.species_hebrew || photo.species_he,
            species_latin: photo.ai?.species_latin || photo.species_la,
            category: photo.ai?.category || photo.category,
            tags: photo.ai?.tags || photo.tags,
            description: photo.ai?.description || photo.description
          },
          instruction: instruction
        };

        const res = await fetch('/api/refine-batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: [item] })
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.error || 'שגיאה ב-AI');
        }

        const results = await res.json();
        if (results && results.length > 0) {
          applyUpdatedAiData(photo, results[0]);
          delete pendingNotes[photo.id];
          savePendingNotesToStorage();
          await persistPhoto(photo);
          alert('✨ התמונה עודכנה ונשמרה בהצלחה!');
        }
      } catch (err) {
        alert('שגיאה בתהליך ה-AI: ' + err.message);
      } finally {
        btn.disabled = false;
        loader.classList.add('hidden');
      }
    }

    async function processPendingBatch() {
      const keys = Object.keys(pendingNotes);
      if (keys.length === 0) {
        alert('אין הערות ממתינות לשליחה כרגע.');
        return;
      }

      // Show clear visual progress modal
      const modal = document.getElementById('batchProgressModal');
      const progressText = document.getElementById('batchModalText');
      const progressBar = document.getElementById('batchModalProgressBar');
      const modalSubtext = document.getElementById('batchModalSubtext');

      modal.classList.remove('hidden');
      modal.classList.add('flex');

      const BATCH_SIZE = 10;
      const totalPhotos = keys.length;
      let processedTotal = 0;

      try {
        for (let i = 0; i < totalPhotos; i += BATCH_SIZE) {
          const chunkIds = keys.slice(i, i + BATCH_SIZE);
          const chunkItems = chunkIds.map(id => {
            const p = photos.find(x => x.id === id);
            return {
              photo_id: id,
              context: {
                title: p?.ai?.title || p?.title || '',
                species_hebrew: p?.ai?.species_hebrew || p?.species_he || '',
                species_latin: p?.ai?.species_latin || p?.species_la || '',
                category: p?.ai?.category || p?.category || 'wildlife',
                tags: p?.ai?.tags || p?.tags || [],
                description: p?.ai?.description || p?.description || ''
              },
              instruction: pendingNotes[id]
            };
          });

          const currentBatchNum = Math.floor(i / BATCH_SIZE) + 1;
          const totalBatches = Math.ceil(totalPhotos / BATCH_SIZE);
          progressText.innerText = `מעבד קבוצה ${currentBatchNum} מתוך ${totalBatches}... (${Math.min(i + BATCH_SIZE, totalPhotos)} / ${totalPhotos} תמונות)`;
          modalSubtext.innerText = `פונה ל-Gemini 3.1 לעדכון פרטי התמונות...`;

          const res = await fetch('/api/refine-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: chunkItems })
          });

          if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'שגיאה בשרת ה-AI');
          }

          const results = await res.json();
          results.forEach(resItem => {
            const photo = photos.find(p => p.id === resItem.photo_id);
            if (photo) {
              applyUpdatedAiData(photo, resItem);
              delete pendingNotes[photo.id];
              processedTotal++;
            }
          });

          // Save whole updated database to disk
          await fetch('/api/save-all-photos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(photos)
          });

          savePendingNotesToStorage();
          renderSidebar();

          const pct = Math.round((processedTotal / totalPhotos) * 100);
          progressBar.style.width = pct + '%';
        }

        progressText.innerText = `🎉 הושלם בהצלחה!`;
        modalSubtext.innerText = `עודכנו ונשמרו ${processedTotal} תמונות. המודאל ייסגר מיד.`;
        setTimeout(() => {
          modal.classList.add('hidden');
          modal.classList.remove('flex');
        }, 1500);

      } catch (err) {
        alert('שגיאה במהלך שליחת ה-Batch: ' + err.message);
        modal.classList.add('hidden');
        modal.classList.remove('flex');
      } finally {
        savePendingNotesToStorage();
        renderSidebar();
        if (currentPhotoId) selectPhoto(currentPhotoId);
      }
    }

    function applyUpdatedAiData(photo, updated) {
      if (!photo.ai) photo.ai = {};
      photo.ai.title = updated.title || photo.ai.title;
      photo.ai.species_hebrew = updated.species_hebrew || photo.ai.species_hebrew;
      photo.ai.species_latin = updated.species_latin || photo.ai.species_latin;
      photo.ai.category = updated.category || photo.ai.category;
      photo.ai.behavior = updated.behavior || photo.ai.behavior || [];
      photo.ai.tags = updated.tags || photo.ai.tags;
      photo.ai.description = updated.description || photo.ai.description;
      photo.last_edited_at = new Date().toISOString();
    }

    async function saveDirectForm() {
      const photo = photos.find(p => p.id === currentPhotoId);
      if (!photo) return;

      const title = document.getElementById('formTitle').value;
      const species_he = document.getElementById('formSpeciesHe').value;
      const species_la = document.getElementById('formSpeciesLa').value;
      const category = document.getElementById('formCategory').value;
      const tags = document.getElementById('formTags').value.split(',').map(t => t.trim()).filter(Boolean);
      const desc = document.getElementById('formDescription').value;

      if (photo.ai) {
        photo.ai.title = title;
        photo.ai.species_hebrew = species_he;
        photo.ai.species_latin = species_la;
        photo.ai.category = category;
        photo.ai.tags = tags;
        photo.ai.description = desc;
      } else {
        photo.title = title;
        photo.species_he = species_he;
        photo.species_la = species_la;
        photo.category = category;
        photo.tags = tags;
        photo.description = desc;
      }

      if (!photo.exif) photo.exif = {};
      if (photo.exif.camera_model !== undefined) {
        photo.exif.camera_model = document.getElementById('formCamera').value;
        photo.exif.lens_model = document.getElementById('formLens').value;
        photo.exif.focal_length = document.getElementById('formFocal').value;
        photo.exif.aperture = document.getElementById('formAperture').value;
        photo.exif.shutter_speed = document.getElementById('formShutter').value;
      } else {
        photo.exif.camera = document.getElementById('formCamera').value;
        photo.exif.lens = document.getElementById('formLens').value;
        photo.exif.focalLength = document.getElementById('formFocal').value;
        photo.exif.aperture = document.getElementById('formAperture').value;
        photo.exif.shutterSpeed = document.getElementById('formShutter').value;
      }

      photo.last_edited_at = new Date().toISOString();

      await persistPhoto(photo);
    }

    async function persistPhoto(updatedPhoto) {
      const res = await fetch('/api/update-photo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedPhoto)
      });

      if (res.ok) {
        showSaveToast();
        selectPhoto(currentPhotoId);
      } else {
        alert('שגיאה בשמירת הנתונים');
      }
    }

    function showSaveToast() {
      const el = document.getElementById('saveStatus');
      el.classList.remove('hidden');
      setTimeout(() => el.classList.add('hidden'), 2500);
    }

    loadData();
  </script>
</body>
</html>
"""

class GalleryAdminHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif path == "/api/photos":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            photos = load_photos()
            self.wfile.write(json.dumps(photos, ensure_ascii=False).encode("utf-8"))
        elif path.startswith("/photos/"):
            rel_path = path.lstrip("/").replace("/", os.sep)
            local_file = os.path.join(PUBLIC_DIR, rel_path)
            if os.path.exists(local_file) and os.path.isfile(local_file):
                self.send_response(200)
                if local_file.endswith(".webp"):
                    self.send_header("Content-Type", "image/webp")
                elif local_file.endswith(".jpg") or local_file.endswith(".jpeg"):
                    self.send_header("Content-Type", "image/jpeg")
                elif local_file.endswith(".png"):
                    self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(local_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body) if body else {}

        if parsed.path == "/api/update-photo":
            photos = load_photos()
            updated_id = data.get("id")
            for idx, p in enumerate(photos):
                if p["id"] == updated_id:
                    photos[idx] = data
                    break
            save_photos(photos)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        elif parsed.path == "/api/save-all-photos":
            save_photos(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        elif parsed.path == "/api/refine-batch":
            try:
                items = data.get("items", [])
                results = refine_batch_with_gemini(items, model_name="gemini-3.1-flash-lite")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(results, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                err_resp = {"error": str(e)}
                self.wfile.write(json.dumps(err_resp, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    print(f"Admin Tool running at: http://localhost:{PORT}")
    with socketserver.TCPServer(("", PORT), GalleryAdminHandler) as httpd:
        httpd.serve_forever()
