// firebase.js - Central Firebase configuration, Auth & Firestore services
import { initializeApp, getApps, getApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged
} from 'firebase/auth';
import {
  getFirestore,
  doc,
  getDoc,
  setDoc,
  updateDoc,
  collection,
  onSnapshot,
  query,
  where,
  orderBy,
  getDocs,
  addDoc,
  deleteDoc,
  serverTimestamp,
  increment
} from 'firebase/firestore';

export const firebaseConfig = {
  apiKey: "AIzaSyA42fi1KrzhQ1BEUwT-HmxyVLYa9ThH6Aw",
  authDomain: "gallery-df271.firebaseapp.com",
  projectId: "gallery-df271",
  storageBucket: "gallery-df271.firebasestorage.app",
  messagingSenderId: "542654150755",
  appId: "1:542654150755:web:ed60a8f0d362cb889ce056",
  measurementId: "G-QEGEKV0690"
};

export const OWNER_EMAIL = 'roigreenberg@gmail.com';

// Safe SSR / Client initialization
let app = null;
let auth = null;
let db = null;

if (typeof window !== 'undefined') {
  try {
    app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
    auth = getAuth(app);
    db = getFirestore(app);
  } catch (err) {
    console.error('Firebase initialization error:', err);
  }
}

export { app, auth, db };

// Auth helpers
export const isUserOwner = (user) => {
  if (!user || !user.email) return false;
  return user.email.toLowerCase().trim() === OWNER_EMAIL.toLowerCase().trim();
};

export const loginWithGoogle = async () => {
  if (!auth) throw new Error('Firebase Auth is not initialized');
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: 'select_account' });
  const result = await signInWithPopup(auth, provider);
  return result.user;
};

export const logoutUser = async () => {
  if (!auth) return;
  await signOut(auth);
};

export const subscribeToAuth = (callback) => {
  if (!auth) {
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(auth, (user) => {
    callback(user);
  });
};
