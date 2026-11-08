// loggerService.js - Firebase Firestore System & Upload Logging
import { db } from './firebase.js';
import { collection, addDoc, serverTimestamp, query, orderBy, limit, onSnapshot } from 'firebase/firestore';

export const LOG_LEVELS = {
  INFO: 'info',
  WARN: 'warn',
  ERROR: 'error',
  SUCCESS: 'success'
};

/**
 * Log an event to console and Firestore `system_logs` collection
 */
export const logEvent = async (level, category, message, details = {}) => {
  const ts = new Date().toLocaleTimeString('he-IL');
  const logPrefix = `[${ts}] [${category.toUpperCase()}] [${level.toUpperCase()}]`;

  if (level === LOG_LEVELS.ERROR) {
    console.error(logPrefix, message, details);
  } else if (level === LOG_LEVELS.WARN) {
    console.warn(logPrefix, message, details);
  } else {
    console.log(logPrefix, message, details);
  }

  if (!db) return;

  try {
    const colRef = collection(db, 'system_logs');
    // Sanitize details so no File or raw non-serializable objects are passed
    const cleanDetails = {};
    for (const k in details) {
      const v = details[k];
      if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
        cleanDetails[k] = v;
      } else if (v && typeof v === 'object' && !(v instanceof File) && !(v instanceof Blob)) {
        try {
          cleanDetails[k] = JSON.parse(JSON.stringify(v));
        } catch (e) {
          cleanDetails[k] = String(v);
        }
      } else if (v instanceof File) {
        cleanDetails[k] = `File: ${v.name} (${Math.round(v.size / 1024)}KB)`;
      }
    }

    await addDoc(colRef, {
      level,
      category,
      message,
      details: cleanDetails,
      created_at: serverTimestamp(),
      client_time: ts,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : ''
    });
  } catch (err) {
    console.warn('Failed to write log to Firestore:', err);
  }
};

/**
 * Real-time listener for the latest system logs
 */
export const subscribeToSystemLogs = (callback, maxLogs = 50) => {
  if (!db) {
    callback([]);
    return () => {};
  }

  const colRef = collection(db, 'system_logs');
  const q = query(colRef, orderBy('created_at', 'desc'), limit(maxLogs));

  return onSnapshot(q, (snapshot) => {
    const logs = [];
    snapshot.forEach(docSnap => {
      logs.push({
        id: docSnap.id,
        ...docSnap.data()
      });
    });
    callback(logs);
  }, (err) => {
    console.warn('System logs listener error:', err);
    callback([]);
  });
};
