// curationService.js - Exhibition & Photo Wall Curation Service
import {
  db,
  isUserOwner
} from './firebase.js';
import {
  doc,
  getDoc,
  getDocs,
  setDoc,
  updateDoc,
  collection,
  query,
  where,
  orderBy,
  onSnapshot,
  addDoc,
  deleteDoc,
  serverTimestamp
} from 'firebase/firestore';

/**
 * Curation item schema:
 * {
 *   id: string, // photo_id
 *   photo_id: string,
 *   photo_data: { title, title_en, thumbnail, display, species_he, species_en, category, exif },
 *   area: 'exhibition' | 'wall' | 'pool', // תערוכה | קיר תמונות | מאגר כללי
 *   status: 'sure' | 'maybe' | 'group' | 'pool' | 'rejected', // בטוחה | אפשרית | תת-קבוצה | במאגר | נפסלה
 *   group_id: string | null, // ID of sub-group if status === 'group'
 *   group_name: string | null,
 *   votes: { [uid]: { score: 2 | 1 | 0 | -1, user_name, user_photo, updated_at } },
 *   ai_critique: string | null,
 *   notes: string,
 *   created_at: timestamp,
 *   updated_at: timestamp
 * }
 */

/**
 * Add or update photo in curation pool
 */
export const addPhotoToCuration = async (photo, area = 'pool', status = 'pool', groupId = null, groupName = null) => {
  if (!db) throw new Error('Database not connected');
  const cleanId = String(photo.id).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);

  const existing = await getDoc(docRef);
  if (existing.exists()) {
    await updateDoc(docRef, {
      area,
      status,
      group_id: groupId,
      group_name: groupName,
      updated_at: serverTimestamp()
    });
  } else {
    await setDoc(docRef, {
      photo_id: photo.id,
      photo_data: {
        id: photo.id,
        title: photo.title || photo.title_en || 'ללא כותרת',
        title_en: photo.title_en || '',
        thumbnail: photo.thumbnail || '',
        display: photo.display || '',
        species_he: photo.species_he || '',
        species_en: photo.species_en || '',
        category: photo.category || photo.categoryHe || 'wildlife',
        humorous_description: photo.humorous_description || '',
        exif: photo.exif || {}
      },
      area,
      status,
      group_id: groupId,
      group_name: groupName,
      votes: {},
      ai_critique: null,
      notes: '',
      created_at: serverTimestamp(),
      updated_at: serverTimestamp()
    });
  }
};

/**
 * Batch import photos to curation pool
 */
export const batchAddPhotosToCuration = async (photos, area = 'pool', status = 'pool') => {
  if (!db) return;
  const promises = photos.map(p => addPhotoToCuration(p, area, status));
  await Promise.all(promises);
};

/**
 * Update curation item status or area
 */
export const updateCurationStatus = async (photoId, { area, status, groupId = null, groupName = null }, photoData = null) => {
  if (!db) throw new Error('Database not connected');
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);

  const updates = {
    updated_at: serverTimestamp()
  };
  if (area !== undefined) updates.area = area;
  if (status !== undefined) updates.status = status;
  if (groupId !== undefined) updates.group_id = groupId;
  if (groupName !== undefined) updates.group_name = groupName;

  if (photoData) {
    const snap = await getDoc(docRef);
    if (!snap.exists()) {
      await setDoc(docRef, {
        photo_id: photoId,
        photo_data: photoData,
        area: area || 'exhibition',
        status: status || 'pool',
        group_id: groupId,
        group_name: groupName,
        votes: {},
        ai_critique: null,
        notes: '',
        created_at: serverTimestamp(),
        updated_at: serverTimestamp()
      });
      return;
    }
  }

  await setDoc(docRef, updates, { merge: true });
};

/**
 * Cast a vote on a curation item
 * score:
 *  +2: 🔥 חובה בתערוכה
 *  +1: 👍 מוצלחת מאוד
 *   0: 🤔 ניטרלי / מתלבט
 *  -1: 👎 פחות מתאים
 */
export const voteOnCurationItem = async (photoId, user, score, photoData = null) => {
  if (!db || !user) throw new Error('Must be logged in to vote');
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);

  const voterInfo = {
    score,
    user_name: user.displayName || user.email?.split('@')[0] || 'מדרג',
    user_photo: user.photoURL || '',
    user_email: user.email || '',
    timestamp: Date.now()
  };

  const snap = await getDoc(docRef);
  if (!snap.exists() && photoData) {
    // CRITICAL: Voting MUST NEVER promote a photo to 'sure' (מועמדות בטוחות)!
    // Only explicit action by the owner can move photos between statuses.
    // Default status: 'maybe' for exhibition_score === 2, or 'pool' for score === 1.
    const initialStatus = photoData.status && photoData.status !== 'sure'
      ? photoData.status
      : (photoData.exhibition_score === 2 ? 'maybe' : 'pool');

    await setDoc(docRef, {
      photo_id: photoId,
      photo_data: photoData,
      area: photoData.area || 'exhibition',
      status: initialStatus,
      group_id: null,
      group_name: null,
      votes: {
        [user.uid]: voterInfo
      },
      ai_critique: null,
      notes: '',
      created_at: serverTimestamp(),
      updated_at: serverTimestamp()
    });
    return;
  }

  // If document already exists, ONLY update this user's vote.
  // NEVER modify status or area on a vote!
  await setDoc(docRef, {
    votes: {
      [user.uid]: voterInfo
    },
    updated_at: serverTimestamp()
  }, { merge: true });
};

/**
 * Restore photos that were accidentally promoted to 'sure' by votes back to their intended initial status ('maybe' or 'pool').
 * Preserves all votes, voter identities, notes, and AI critiques intact.
 */
export const revertAccidentalSureItems = async (user) => {
  if (!db || !isUserOwner(user)) throw new Error('Only the owner can revert sure items');

  const colRef = collection(db, 'curation_items');
  const q = query(colRef, where('status', '==', 'sure'));
  const snap = await getDocs(q);

  let count = 0;
  const updates = [];

  snap.forEach(d => {
    const data = d.data();
    // 2 -> 'maybe' (מועמדות אפשריות), 1 or other -> 'pool' (מאגר לתערוכה)
    const origScore = data.photo_data?.exhibition_score || 1;
    const targetStatus = origScore === 2 ? 'maybe' : 'pool';

    updates.push(
      updateDoc(d.ref, {
        status: targetStatus,
        updated_at: serverTimestamp()
      })
    );
    count++;
  });

  await Promise.all(updates);
  return count;
};

/**
 * Remove vote
 */
export const removeVoteOnCurationItem = async (photoId, user) => {
  if (!db || !user) return;
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);
  const snap = await getDoc(docRef);
  if (!snap.exists()) return;

  const data = snap.data();
  const votes = data.votes || {};
  delete votes[user.uid];

  await updateDoc(docRef, {
    votes,
    updated_at: serverTimestamp()
  });
};

/**
 * Save Gemini critique to a photo
 */
export const saveGeminiCritique = async (photoId, critiqueText) => {
  if (!db) return;
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);
  await updateDoc(docRef, {
    ai_critique: critiqueText,
    updated_at: serverTimestamp()
  });
};

/**
 * Remove from curation entirely
 */
export const removeCurationItem = async (photoId) => {
  if (!db) return;
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  await deleteDoc(doc(db, 'curation_items', cleanId));
};

/**
 * Real-time listener for all curation items
 */
export const subscribeToCurationItems = (callback) => {
  if (!db) {
    callback([]);
    return () => {};
  }
  const colRef = collection(db, 'curation_items');
  return onSnapshot(colRef, (snapshot) => {
    const items = [];
    snapshot.forEach(docSnap => {
      items.push({
        id: docSnap.id,
        ...docSnap.data()
      });
    });
    callback(items);
  }, (err) => {
    console.warn('Curation listener error:', err);
    callback([]);
  });
};

/**
 * Curation sub-groups collection:
 * schema:
 * {
 *   id: string,
 *   name: string,
 *   area: 'exhibition' | 'wall',
 *   status: 'sure' | 'maybe' | 'pool' | 'rejected', // Acts as a board card
 *   winner_id: string | null,
 *   ai_comparison: string | null,
 *   created_at,
 *   updated_at
 * }
 */
export const createSubGroup = async (name, area = 'exhibition', status = 'maybe') => {
  if (!db) throw new Error('Database not connected');
  const colRef = collection(db, 'curation_groups');
  const docRef = await addDoc(colRef, {
    name: name.trim(),
    area,
    status,
    winner_id: null,
    ai_comparison: null,
    created_at: serverTimestamp(),
    updated_at: serverTimestamp()
  });
  return docRef.id;
};

export const updateSubGroup = async (groupId, data) => {
  if (!db) return;
  const docRef = doc(db, 'curation_groups', groupId);
  await updateDoc(docRef, {
    ...data,
    updated_at: serverTimestamp()
  });
};

export const deleteSubGroup = async (groupId) => {
  if (!db) return;
  await deleteDoc(doc(db, 'curation_groups', groupId));
};

/**
 * Assign a photo to a sub-group
 */
export const assignPhotoToGroup = async (photoId, groupId, groupName, photoData = null) => {
  if (!db) throw new Error('Database not connected');
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);

  const snap = await getDoc(docRef);
  if (!snap.exists() && photoData) {
    await setDoc(docRef, {
      photo_id: photoId,
      photo_data: photoData,
      area: 'exhibition',
      status: 'maybe',
      group_id: groupId,
      group_name: groupName,
      votes: {},
      ai_critique: null,
      notes: '',
      created_at: serverTimestamp(),
      updated_at: serverTimestamp()
    });
    return;
  }

  await setDoc(docRef, {
    group_id: groupId,
    group_name: groupName,
    updated_at: serverTimestamp()
  }, { merge: true });
};

/**
 * Remove a photo from its sub-group
 */
export const removePhotoFromGroup = async (photoId) => {
  if (!db) throw new Error('Database not connected');
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const docRef = doc(db, 'curation_items', cleanId);

  await setDoc(docRef, {
    group_id: null,
    group_name: null,
    updated_at: serverTimestamp()
  }, { merge: true });
};

export const subscribeToSubGroups = (callback) => {
  if (!db) {
    callback([]);
    return () => {};
  }
  const colRef = collection(db, 'curation_groups');
  return onSnapshot(colRef, (snapshot) => {
    const groups = [];
    snapshot.forEach(docSnap => {
      groups.push({
        id: docSnap.id,
        ...docSnap.data()
      });
    });
    callback(groups);
  }, (err) => {
    console.warn('Sub-groups listener error:', err);
    callback([]);
  });
};
