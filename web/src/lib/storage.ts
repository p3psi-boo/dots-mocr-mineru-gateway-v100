import type { TaskRecord, TaskResult } from './types';

const TASKS_KEY = 'dotmocr.tasks.v1';
const DB_NAME = 'dotmocr-webui';
const DB_VERSION = 1;

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

export function loadTasks(): TaskRecord[] {
  try {
    return JSON.parse(localStorage.getItem(TASKS_KEY) ?? '[]') as TaskRecord[];
  } catch {
    return [];
  }
}

export function saveTasks(tasks: TaskRecord[]): void {
  localStorage.setItem(TASKS_KEY, JSON.stringify(tasks));
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
