import type { FileResult, SubmitOptions, TaskRecord, TaskState, TaskStatus } from './types';
import { defaultOptions } from './storage';

export const terminalStates: TaskState[] = ['completed', 'failed', 'expired'];
export const maxFiles = 8;
export const acceptedExtensions = '.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff';
export const supportedFilePattern = /\.(pdf|png|jpe?g|webp|bmp|tiff?)$/i;

export function isCancelled(task: Pick<TaskRecord, 'status' | 'error'>): boolean {
  return task.status === 'failed' && /cancel/i.test(task.error ?? '');
}

export function statusText(status: TaskState, error?: string | null): string {
  if (status === 'failed' && /cancel/i.test(error ?? '')) return '已取消';
  return {
    pending: '排队中',
    processing: '解析中',
    completed: '已完成',
    failed: '失败',
    expired: '已过期'
  }[status];
}

export function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value));
}

export function formatSize(bytes: number): string {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatLogTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
    hour12: false
  }).format(new Date(value));
}

export function optionsSummary(options: SubmitOptions): string {
  const method = { auto: '自动', ocr: 'OCR', txt: '文本' }[options.parseMethod];
  const lang = options.lang === 'en' ? '英文' : '中文';
  const pages =
    options.endPage === null
      ? '全部页'
      : `第 ${options.startPage + 1}–${options.endPage + 1} 页`;
  const extras = [
    options.formula ? '公式' : '',
    options.table ? '表格' : '',
    options.images ? '图片' : ''
  ].filter(Boolean);
  return `${method} · ${lang} · ${pages}${extras.length ? ` · ${extras.join('/')}` : ''}`;
}

export function isOptionsChanged(options: SubmitOptions): boolean {
  return (
    options.lang !== defaultOptions.lang ||
    options.parseMethod !== defaultOptions.parseMethod ||
    options.formula !== defaultOptions.formula ||
    options.table !== defaultOptions.table ||
    options.images !== defaultOptions.images ||
    options.startPage !== 0 ||
    options.endPage !== null
  );
}

export function expandArtifact(artifact?: FileResult): Record<string, unknown> {
  if (!artifact) return {};
  const expanded: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(artifact)) {
    if (typeof value === 'string' && key !== 'md_content') {
      try {
        expanded[key] = JSON.parse(value);
      } catch {
        expanded[key] = value;
      }
    } else {
      expanded[key] = value;
    }
  }
  return expanded;
}

export function mergeStatus(record: TaskRecord, status: TaskStatus): TaskRecord {
  return {
    ...record,
    ...status,
    original_names: record.original_names,
    sizes: record.sizes,
    options: record.options
  };
}
