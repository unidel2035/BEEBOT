/**
 * Оффлайн-хранилище на IndexedDB + очередь синхронизации.
 *
 * Кэширует данные API локально, при отсутствии сети отдаёт кэш.
 * Мутации (PATCH/POST/DELETE) складываются в очередь и
 * отправляются при восстановлении связи.
 */

const DB_NAME = 'beebot-terminal'
const DB_VERSION = 1
const STORE_CACHE = 'cache'
const STORE_QUEUE = 'sync-queue'

let _db = null

function openDB() {
  if (_db) return Promise.resolve(_db)
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (e) => {
      const db = e.target.result
      if (!db.objectStoreNames.contains(STORE_CACHE)) {
        db.createObjectStore(STORE_CACHE)
      }
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        db.createObjectStore(STORE_QUEUE, { keyPath: 'id', autoIncrement: true })
      }
    }
    req.onsuccess = () => { _db = req.result; resolve(_db) }
    req.onerror = () => reject(req.error)
  })
}

// ---------------------------------------------------------------------------
// Кэш данных API
// ---------------------------------------------------------------------------

export async function cacheGet(key) {
  const db = await openDB()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_CACHE, 'readonly')
    const req = tx.objectStore(STORE_CACHE).get(key)
    req.onsuccess = () => resolve(req.result ?? null)
    req.onerror = () => resolve(null)
  })
}

export async function cacheSet(key, value) {
  const db = await openDB()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_CACHE, 'readwrite')
    tx.objectStore(STORE_CACHE).put(value, key)
    tx.oncomplete = () => resolve()
  })
}

// ---------------------------------------------------------------------------
// Очередь синхронизации
// ---------------------------------------------------------------------------

export async function enqueue(action) {
  const db = await openDB()
  const entry = { ...action, createdAt: Date.now() }
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite')
    tx.objectStore(STORE_QUEUE).add(entry)
    tx.oncomplete = () => resolve()
  })
}

export async function getQueue() {
  const db = await openDB()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_QUEUE, 'readonly')
    const req = tx.objectStore(STORE_QUEUE).getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => resolve([])
  })
}

export async function removeFromQueue(id) {
  const db = await openDB()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite')
    tx.objectStore(STORE_QUEUE).delete(id)
    tx.oncomplete = () => resolve()
  })
}

export async function clearQueue() {
  const db = await openDB()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite')
    tx.objectStore(STORE_QUEUE).clear()
    tx.oncomplete = () => resolve()
  })
}

// ---------------------------------------------------------------------------
// Синхронизация очереди
// ---------------------------------------------------------------------------

let _syncing = false

export async function syncQueue(executor) {
  if (_syncing) return
  _syncing = true
  try {
    const items = await getQueue()
    for (const item of items) {
      try {
        await executor(item)
        await removeFromQueue(item.id)
      } catch (e) {
        if (e?.response?.status >= 400 && e?.response?.status < 500) {
          // Некорректный запрос — удалить из очереди, чтобы не блокировать
          await removeFromQueue(item.id)
        } else {
          break // Сеть недоступна — остановить синхронизацию
        }
      }
    }
  } finally {
    _syncing = false
  }
}

// ---------------------------------------------------------------------------
// Network-first fetch с fallback на кэш
// ---------------------------------------------------------------------------

export async function fetchWithCache(key, fetcher) {
  try {
    const data = await fetcher()
    await cacheSet(key, data)
    return { data, offline: false }
  } catch (e) {
    const cached = await cacheGet(key)
    if (cached !== null) {
      return { data: cached, offline: true }
    }
    throw e
  }
}

// ---------------------------------------------------------------------------
// Online/Offline status
// ---------------------------------------------------------------------------

export function isOnline() {
  return navigator.onLine
}
