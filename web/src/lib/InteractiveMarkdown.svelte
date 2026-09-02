<script module lang="ts">
  import { marked } from 'marked';
  import markedKatex from 'marked-katex-extension';
  import 'katex/dist/katex.min.css';

  marked.use(markedKatex({ throwOnError: false }));
</script>

<script lang="ts">
  import DOMPurify from 'dompurify';
  import { tick } from 'svelte';
  import { Check, Clipboard, Download, ExternalLink, Image as ImageIcon } from '@lucide/svelte';
  import { prefersReducedMotion } from '$lib/bbox';
  import {
    blockLabel,
    copyImageCompat,
    copyTextCompat,
    downloadBlob,
    interactiveBlocks,
    resolveImage,
    safeDownloadName
  } from '$lib/interactive-markdown';
  import type { ContentListItem, FileResult } from '$lib/types';

  let {
    artifact,
    filename,
    selectedIndex = $bindable<number | null>(null)
  }: {
    artifact: FileResult;
    filename: string;
    selectedIndex?: number | null;
  } = $props();

  let actionState = $state('');
  let actionTimer: number | undefined;
  let skipScroll = false;
  let root = $state<HTMLDivElement>();

  const blocks = $derived(interactiveBlocks(artifact));

  function sanitize(html: string): string {
    return DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true, mathMl: true },
      ADD_ATTR: ['target', 'rel']
    });
  }

  function richText(value = '', inline = false): string {
    const html = inline ? marked.parseInline(value) : marked.parse(value);
    return sanitize(html as string).replace(
      /<a\s/gi,
      '<a target="_blank" rel="noopener noreferrer" '
    );
  }

  function tableHtml(value = ''): string {
    return richText(value);
  }

  function equationHtml(value = ''): string {
    return richText(`$$\n${value}\n$$`);
  }

  function select(index: number): void {
    skipScroll = true;
    selectedIndex = selectedIndex === index ? null : index;
  }

  function announce(message: string): void {
    actionState = message;
    if (actionTimer) window.clearTimeout(actionTimer);
    actionTimer = window.setTimeout(() => (actionState = ''), 1800);
  }

  async function copyText(value: string, message = '已复制'): Promise<void> {
    announce((await copyTextCompat(value)) ? message : '复制失败');
  }

  function tableMatrix(container: HTMLElement): string[][] {
    const rows = Array.from(container.querySelectorAll('table tr'));
    if (!rows.length) return container.innerText.split('\n').filter(Boolean).map((line) => [line]);
    return rows.map((row) =>
      Array.from(row.querySelectorAll('th, td')).map((cell) => (cell.textContent ?? '').trim())
    );
  }

  function quoteCsv(value: string): string {
    return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
  }

  async function copyTable(event: MouseEvent): Promise<void> {
    event.stopPropagation();
    const block = (event.currentTarget as HTMLElement).closest('.interactive-block') as HTMLElement;
    const text = tableMatrix(block).map((row) => row.join('\t')).join('\n');
    await copyText(text, '表格已复制');
  }

  async function copyBlockText(event: MouseEvent, value: string): Promise<void> {
    event.stopPropagation();
    await copyText(value, '文本已复制');
  }

  function exportTable(event: MouseEvent, index: number): void {
    event.stopPropagation();
    const block = (event.currentTarget as HTMLElement).closest('.interactive-block') as HTMLElement;
    const csv = tableMatrix(block).map((row) => row.map(quoteCsv).join(',')).join('\r\n');
    downloadBlob(`\ufeff${csv}`, 'text/csv;charset=utf-8', safeDownloadName(`${filename}-table-${index + 1}`, 'csv'));
    announce('表格已导出');
  }

  async function copyImage(event: MouseEvent, source: string): Promise<void> {
    event.stopPropagation();
    const result = await copyImageCompat(source);
    announce(result === 'image' ? '图片已复制' : result === 'source' ? '图片地址已复制' : '复制失败');
  }

  function openImage(event: MouseEvent, source: string): void {
    event.stopPropagation();
    window.open(source, '_blank', 'noopener,noreferrer');
  }

  function textFor(block: ContentListItem): string {
    return typeof block.text === 'string' ? block.text : '';
  }

  $effect(() => {
    const index = selectedIndex;
    if (index === null || !root) return;
    if (skipScroll) {
      skipScroll = false;
      return;
    }
    void tick().then(() => {
      root
        ?.querySelector(`[data-block-index="${index}"]`)
        ?.scrollIntoView({ block: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
    });
  });
</script>

<div
  class="interactive-markdown"
  bind:this={root}
  aria-label="交互式 Markdown 文档"
>
  {#if blocks.length}
    {#each blocks as block, index (`${block.page_idx ?? 0}-${index}`)}
      {@const type = String(block.type ?? 'text')}
      {@const selected = selectedIndex === index}
      {@const imageSource = type === 'image' ? resolveImage(artifact, String(block.img_path ?? '')) : ''}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_click_events_have_key_events -->
      <article
        class="interactive-block type-{type}"
        class:selected
        data-block-index={index}
        data-page={block.page_idx ?? 0}
        id={`md-block-${index}`}
        aria-label={`${blockLabel(type)}，第 ${(block.page_idx ?? 0) + 1} 页${selected ? '，已选中' : ''}`}
        onclick={() => select(index)}
        onkeydown={(event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          if ((event.target as HTMLElement).closest('button, a, input, textarea')) return;
          event.preventDefault();
          select(index);
        }}
      >
        <div class="element-meta" aria-hidden={!selected}>
          <span>{blockLabel(type)}</span>
          <small>P{(block.page_idx ?? 0) + 1}</small>
        </div>

        {#if type === 'text'}
          <div class="element-actions">
            <button type="button" title="复制文本" aria-label="复制文本" onclick={(event) => copyBlockText(event, textFor(block))}><Clipboard size={14} />复制文本</button>
          </div>
          {#if block.text_level === 1}
            <h1>{@html richText(textFor(block), true)}</h1>
          {:else if block.text_level === 2}
            <h2>{@html richText(textFor(block), true)}</h2>
          {:else if block.text_level === 3}
            <h3>{@html richText(textFor(block), true)}</h3>
          {:else}
            <div class="rich-text">{@html richText(textFor(block))}</div>
          {/if}
        {:else if type === 'list'}
          <ul>
            {#each block.list_items ?? [textFor(block)] as item}
              <li>{@html richText(String(item).replace(/^[-*+]\s+/, ''), true)}</li>
            {/each}
          </ul>
        {:else if type === 'table'}
          <div class="element-actions">
            <button type="button" title="复制表格" aria-label="复制表格" onclick={copyTable}><Clipboard size={14} />复制</button>
            <button type="button" title="导出 CSV" aria-label="导出 CSV" onclick={(event) => exportTable(event, index)}><Download size={14} />导出 CSV</button>
          </div>
          <div class="table-shell">{@html tableHtml(String(block.table_body ?? block.text ?? ''))}</div>
        {:else if type === 'equation'}
          <div class="equation">{@html equationHtml(textFor(block))}</div>
        {:else if type === 'image'}
          <div class="element-actions">
            <button type="button" disabled={!imageSource} title="复制图片" aria-label="复制图片" onclick={(event) => copyImage(event, imageSource)}><ImageIcon size={14} />复制图片</button>
            <button type="button" disabled={!imageSource} title="在新标签页打开图片" aria-label="在新标签页打开图片" onclick={(event) => openImage(event, imageSource)}><ExternalLink size={14} />打开</button>
          </div>
          {#if imageSource}
            <img src={imageSource} alt={String(block.alt ?? `文档图片 ${index + 1}`)} />
          {:else}
            <div class="missing-image"><ImageIcon size={22} /><span>图片数据未返回</span></div>
          {/if}
        {:else if type === 'header' || type === 'footer' || type === 'page_footnote'}
          <div class="document-note">{@html richText(textFor(block))}</div>
        {:else}
          <div class="rich-text">{@html richText(textFor(block))}</div>
        {/if}
      </article>
    {/each}
  {:else if artifact.md_content}
    <article class="interactive-block fallback-markdown" role="listitem">
      <div class="rich-text">{@html richText(artifact.md_content)}</div>
    </article>
  {:else}
    <div class="interactive-empty">JSON 结果中没有可渲染的元素</div>
  {/if}
</div>

{#if actionState}
  <div class="action-toast" role="status"><Check size={14} />{actionState}</div>
{/if}
