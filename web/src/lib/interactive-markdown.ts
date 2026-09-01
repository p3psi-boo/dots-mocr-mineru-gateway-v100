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
    return page.blocks.filter(isBlock).map((block) => {
      const category = String(block.category ?? 'Text');
      const type = categoryTypes[category] ?? 'text';
      const item: ContentListItem = {
        type,
        page_idx: pageIdx,
        bbox: Array.isArray(block.bbox) ? block.bbox.filter((value): value is number => typeof value === 'number') : undefined,
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

export function interactiveBlocks(artifact: FileResult): ContentListItem[] {
  const contentList = parseJson(artifact.content_list);
  if (Array.isArray(contentList)) {
    const blocks = contentList.filter(isBlock).map((item) => item as ContentListItem);
    if (blocks.length) return blocks;
  }
  return fromModelOutput(artifact);
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
