import type { ContentListItem, FileResult } from '$lib/types';

const categoryTypes: Record<string, string> = {
  Title: 'text',
  'Section-header': 'text',
  Text: 'text',
  Caption: 'text',
  Table: 'table',
  Formula: 'equation',
  'List-item': 'list',
  Picture: 'image',
  'Page-header': 'header',
  'Page-footer': 'footer',
  Footnote: 'page_footnote'
};

function parseJson(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

function isBlock(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function fromModelOutput(artifact: FileResult): ContentListItem[] {
  const parsed = parseJson(artifact.model_output);
  if (!Array.isArray(parsed)) return [];

  return parsed.flatMap((page, pageIndex) => {
    if (!isBlock(page) || !Array.isArray(page.blocks)) return [];
    const pageIdx = typeof page.page_idx === 'number' ? page.page_idx : pageIndex;
    const pageWidth = typeof page.width === 'number' ? page.width : 0;
    const pageHeight = typeof page.height === 'number' ? page.height : 0;
    return page.blocks.filter(isBlock).map((block) => {
      const category = String(block.category ?? 'Text');
      const type = categoryTypes[category] ?? 'text';
      const item: ContentListItem = {
        type,
        page_idx: pageIdx,
        bbox: normalizeBbox(block.bbox, pageWidth, pageHeight),
        text: String(block.text ?? '')
      };
      if (category === 'Title') item.text_level = 1;
      if (category === 'Section-header') item.text_level = 2;
      if (type === 'table') item.table_body = item.text;
      if (type === 'list') item.list_items = [item.text ?? ''];
      return item;
    });
  });
}

function normalizeBbox(value: unknown, width: number, height: number): number[] | undefined {
  if (!Array.isArray(value) || value.length !== 4) return undefined;
  const bbox = value.filter((item): item is number => typeof item === 'number');
  if (bbox.length !== 4) return undefined;
  const max = Math.max(...bbox);
  if (max <= 1000 || width <= 0 || height <= 0) return bbox;
  return [
    (bbox[0] * 1000) / width,
    (bbox[1] * 1000) / height,
    (bbox[2] * 1000) / width,
    (bbox[3] * 1000) / height
  ];
}

export function interactiveBlocks(artifact: FileResult): ContentListItem[] {
  const contentList = parseJson(artifact.content_list);
  if (Array.isArray(contentList)) {
    const blocks = contentList.filter(isBlock).map((item) => item as ContentListItem);
    if (blocks.length) return blocks;
  }
  return fromModelOutput(artifact);
}

export interface OutlineEntry {
  index: number;
  page: number;
  label: string;
  level: number;
}

export function documentOutline(blocks: ContentListItem[]): OutlineEntry[] {
  const entries: OutlineEntry[] = [];
  let lastPage = -1;
  blocks.forEach((block, index) => {
    const page = block.page_idx ?? 0;
    if (page !== lastPage) {
      entries.push({ index, page, label: `第 ${page + 1} 页`, level: 0 });
      lastPage = page;
    }
    const level = typeof block.text_level === 'number' ? block.text_level : 0;
    if (level >= 1 && block.text) {
      entries.push({
        index,
        page,
        label: String(block.text).replace(/\s+/g, ' ').trim().slice(0, 48),
        level
      });
    }
  });
  return entries;
}

export function blockLabel(type: string): string {
  return {
    text: '文本',
    table: '表格',
    equation: '公式',
    list: '列表',
    image: '图片',
    header: '页眉',
    footer: '页脚',
    page_footnote: '脚注'
  }[type] ?? type;
}

export function resolveImage(artifact: FileResult, path = ''): string {
  if (!path) return '';
  const name = path.split('/').pop() ?? path;
  return artifact.images?.[name] ?? artifact.images?.[path] ?? path;
}

export function safeDownloadName(value: string, extension: string): string {
  const stem = value.replace(/\.[^.]+$/, '').replace(/[\\/:*?\"<>|]+/g, '-').trim() || 'document';
  return `${stem}.${extension}`;
}

export function downloadBlob(content: BlobPart, type: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export async function copyTextCompat(value: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // HTTP origins commonly reject the modern Clipboard API. Fall through
      // to the synchronous selection-based path while the click is active.
    }
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.readOnly = true;
  textarea.setAttribute('aria-hidden', 'true');
  textarea.style.position = 'fixed';
  textarea.style.inset = '0 auto auto -9999px';
  textarea.style.opacity = '0';
  document.body.append(textarea);
  textarea.focus({ preventScroll: true });
  textarea.select();
  textarea.setSelectionRange(0, value.length);
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  } finally {
    textarea.remove();
  }
  return copied;
}

export async function copyImageCompat(source: string): Promise<'image' | 'source' | false> {
  if (!source) return false;
  if (window.isSecureContext && navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
    try {
      const blob = await (await fetch(source)).blob();
      await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
      return 'image';
    } catch {
      // Continue with execCommand for non-secure HTTP deployments.
    }
  }

  const container = document.createElement('div');
  const image = document.createElement('img');
  container.contentEditable = 'true';
  container.setAttribute('aria-hidden', 'true');
  container.style.position = 'fixed';
  container.style.inset = '0 auto auto -9999px';
  container.append(image);
  image.src = source;
  document.body.append(container);

  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNode(image);
  selection?.removeAllRanges();
  selection?.addRange(range);
  let copiedImage = false;
  try {
    copiedImage = document.execCommand('copy');
  } catch {
    copiedImage = false;
  } finally {
    selection?.removeAllRanges();
    container.remove();
  }
  if (copiedImage) return 'image';
  return (await copyTextCompat(source)) ? 'source' : false;
}
