import type { SubmitOptions, TaskRecord, TaskResult, ThemePreference } from './types';

const TASKS_KEY = 'dotmocr.tasks.v1';
const OPTIONS_KEY = 'dotmocr.options.v2';
const THEME_KEY = 'dotmocr.theme.v1';
const DB_NAME = 'dotmocr-webui';
const DB_VERSION = 1;

export const defaultOptions: SubmitOptions = {
  lang: 'ch',
  parseMethod: 'auto',
  formula: true,
  table: true,
  images: true,
  startPage: 0,
  endPage: null
};

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains('files')) {
        database.createObjectStore('files');
      }
      if (!database.objectStoreNames.contains('results')) {
        database.createObjectStore('results');
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function put(storeName: string, key: IDBValidKey, value: unknown): Promise<void> {
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(storeName, 'readwrite');
    transaction.objectStore(storeName).put(value, key);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

async function get<T>(storeName: string, key: IDBValidKey): Promise<T | undefined> {
  const database = await openDatabase();
  const value = await new Promise<T | undefined>((resolve, reject) => {
    const request = database.transaction(storeName).objectStore(storeName).get(key);
    request.onsuccess = () => resolve(request.result as T | undefined);
    request.onerror = () => reject(request.error);
  });
  database.close();
  return value;
}

async function del(storeName: string, key: IDBValidKey): Promise<void> {
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(storeName, 'readwrite');
    transaction.objectStore(storeName).delete(key);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

export function loadTasks(): TaskRecord[] {
  try {
    return JSON.parse(localStorage.getItem(TASKS_KEY) ?? '[]') as TaskRecord[];
  } catch {
    return [];
  }
}

export function saveTasks(tasks: TaskRecord[]): void {
  try {
    localStorage.setItem(TASKS_KEY, JSON.stringify(tasks));
  } catch {
    throw new Error('本地存储已满，请清理已完成的任务');
  }
}

export function loadOptions(): SubmitOptions {
  try {
    const raw = JSON.parse(localStorage.getItem(OPTIONS_KEY) ?? 'null') as Partial<SubmitOptions> | null;
    if (!raw || typeof raw !== 'object') return { ...defaultOptions };
    return {
      lang: raw.lang === 'en' ? 'en' : 'ch',
      parseMethod: raw.parseMethod === 'ocr' || raw.parseMethod === 'txt' ? raw.parseMethod : 'auto',
      formula: raw.formula !== false,
      table: raw.table !== false,
      images: raw.images !== false,
      startPage: typeof raw.startPage === 'number' && raw.startPage >= 0 ? raw.startPage : 0,
      endPage: typeof raw.endPage === 'number' && raw.endPage >= 0 ? raw.endPage : null
    };
  } catch {
    return { ...defaultOptions };
  }
}

export function saveOptions(options: SubmitOptions): void {
  try {
    localStorage.setItem(OPTIONS_KEY, JSON.stringify(options));
  } catch {
    // Preferences are non-critical if quota is exhausted.
  }
}

export function loadTheme(): ThemePreference {
  const value = localStorage.getItem(THEME_KEY);
  if (value === 'light' || value === 'dark' || value === 'system') return value;
  return 'system';
}

export function saveTheme(theme: ThemePreference): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Theme preference is non-critical if quota is exhausted.
  }
}

export function resolvedTheme(theme: ThemePreference): 'light' | 'dark' {
  if (theme === 'light' || theme === 'dark') return theme;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyTheme(theme: ThemePreference): void {
  const resolved = resolvedTheme(theme);
  document.documentElement.dataset.theme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute(
    'content',
    resolved === 'dark' ? '#121412' : '#f6f6f3'
  );
}

export async function saveFiles(taskId: string, files: File[]): Promise<void> {
  await Promise.all(files.map((file, index) => put('files', `${taskId}:${index}`, file)));
}

export function loadFile(taskId: string, index: number): Promise<File | undefined> {
  return get<File>('files', `${taskId}:${index}`);
}

export function saveResult(taskId: string, result: TaskResult): Promise<void> {
  return put('results', taskId, result);
}

export function loadResult(taskId: string): Promise<TaskResult | undefined> {
  return get<TaskResult>('results', taskId);
}

export async function deleteTaskAssets(taskId: string, fileCount: number): Promise<void> {
  const count = Math.max(fileCount, 1);
  await Promise.all([
    ...Array.from({ length: count }, (_, index) => del('files', `${taskId}:${index}`)),
    del('results', taskId)
  ]);
}
