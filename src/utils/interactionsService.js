// interactionsService.js - Firebase Firestore likes and comments service
import {
  db,
  isUserOwner
} from './firebase.js';
import {
  doc,
  getDoc,
  setDoc,
  updateDoc,
  collection,
  query,
  where,
  orderBy,
  onSnapshot,
  addDoc,
  deleteDoc,
  serverTimestamp,
  increment
} from 'firebase/firestore';

/**
 * Toggle like for a photo by current user
 */
export const togglePhotoLike = async (photoId, user) => {
  if (!db || !user) throw new Error('Must be logged in to like photos');

  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const likeDocRef = doc(db, 'photo_likes', cleanId);

  const snap = await getDoc(likeDocRef);
  let isLiked = false;
  let count = 0;

  if (snap.exists()) {
    const data = snap.data();
    const likedBy = data.liked_by || {};
    isLiked = Boolean(likedBy[user.uid]);
    count = data.count || 0;

    if (isLiked) {
      // Unlike
      delete likedBy[user.uid];
      const newCount = Math.max(0, count - 1);
      await updateDoc(likeDocRef, {
        [`liked_by.${user.uid}`]: false,
        count: newCount,
        updated_at: serverTimestamp()
      });
      return { isLiked: false, count: newCount };
    } else {
      // Like
      await updateDoc(likeDocRef, {
        [`liked_by.${user.uid}`]: true,
        count: count + 1,
        updated_at: serverTimestamp()
      });
      return { isLiked: true, count: count + 1 };
    }
  } else {
    // Document does not exist yet -> create
    await setDoc(likeDocRef, {
      photo_id: photoId,
      count: 1,
      liked_by: {
        [user.uid]: true
      },
      created_at: serverTimestamp(),
      updated_at: serverTimestamp()
    });
    return { isLiked: true, count: 1 };
  }
};

/**
 * Real-time listener for a single photo's likes
 */
export const subscribeToPhotoLikes = (photoId, callback) => {
  if (!db) {
    callback({ count: 0, liked_by: {} });
    return () => {};
  }
  const cleanId = String(photoId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const likeDocRef = doc(db, 'photo_likes', cleanId);

  return onSnapshot(likeDocRef, (snap) => {
    if (snap.exists()) {
      const data = snap.data();
      const count = data.count || 0;
      const liked_by = data.liked_by || {};
      callback({ count, liked_by });
    } else {
      callback({ count: 0, liked_by: {} });
    }
  }, (err) => {
    console.warn('Likes listener error:', err);
    callback({ count: 0, liked_by: {} });
  });
};

/**
 * Real-time listener for all likes map { [photoId]: count }
 */
export const subscribeToAllLikes = (callback) => {
  if (!db) {
    callback({});
    return () => {};
  }
  const colRef = collection(db, 'photo_likes');
  return onSnapshot(colRef, (snapshot) => {
    const map = {};
    snapshot.forEach(docSnap => {
      const d = docSnap.data();
      if (d.photo_id && typeof d.count === 'number') {
        map[d.photo_id] = {
          count: d.count,
          liked_by: d.liked_by || {}
        };
      }
    });
    callback(map);
  }, (err) => {
    console.warn('All likes listener error:', err);
    callback({});
  });
};

/**
 * Add a comment to a photo
 */
export const addPhotoComment = async (photoId, user, text) => {
  if (!db || !user) throw new Error('Must be logged in to comment');
  const cleanText = (text || '').trim();
  if (!cleanText) throw new Error('Comment cannot be empty');

  const colRef = collection(db, 'photo_comments');
  const docRef = await addDoc(colRef, {
    photo_id: photoId,
    user_id: user.uid,
    user_name: user.displayName || user.email.split('@')[0],
    user_photo: user.photoURL || '',
    user_email: user.email,
    text: cleanText,
    created_at: serverTimestamp()
  });

  return docRef.id;
};

/**
 * Real-time listener for photo comments
 */
export const subscribeToPhotoComments = (photoId, callback) => {
  if (!db) {
    callback([]);
    return () => {};
  }

  const colRef = collection(db, 'photo_comments');
  const q = query(
    colRef,
    where('photo_id', '==', photoId)
  );

  return onSnapshot(q, (snapshot) => {
    const comments = [];
    snapshot.forEach(docSnap => {
      comments.push({
        id: docSnap.id,
        ...docSnap.data()
      });
    });
    // Sort client-side by created_at to avoid requiring composite indexes initially
    comments.sort((a, b) => {
      const tA = a.created_at?.toMillis ? a.created_at.toMillis() : 0;
      const tB = b.created_at?.toMillis ? b.created_at.toMillis() : 0;
      return tA - tB;
    });
    callback(comments);
  }, (err) => {
    console.warn('Comments listener error:', err);
    callback([]);
  });
};

/**
 * Delete a comment (by author or owner)
 */
export const deletePhotoComment = async (commentId, user) => {
  if (!db || !user) throw new Error('Permission denied');
  const docRef = doc(db, 'photo_comments', commentId);
  const snap = await getDoc(docRef);
  if (!snap.exists()) return;

  const data = snap.data();
  if (data.user_id !== user.uid && !isUserOwner(user)) {
    throw new Error('You can only delete your own comments');
  }

  await deleteDoc(docRef);
};
