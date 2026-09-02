<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { CircleAlert, LoaderCircle } from '@lucide/svelte';
  import { prefersReducedMotion } from '$lib/bbox';
  import PdfPage from '$lib/PdfPage.svelte';
  import { getDocument, type PDFDocumentProxy } from '$lib/pdf';
  import type { ContentListItem } from '$lib/types';

  let {
    url,
    blocks = [],
    selectedIndex = null,
    zoom = 1,
    onSelectBlock,
    onPageChange
  }: {
    url: string;
    blocks?: ContentListItem[];
    selectedIndex?: number | null;
    zoom?: number;
    onSelectBlock?: (index: number) => void;
    onPageChange?: (page: number, total: number) => void;
  } = $props();

  let root = $state<HTMLDivElement>();
  let pdf = $state<PDFDocumentProxy | null>(null);
  let pageCount = $state(0);
  let metrics = $state<{ width: number; height: number }[]>([]);
  let loadError = $state('');
  let loading = $state(true);
  let containerWidth = $state(640);

  const cssWidth = $derived(Math.max(240, containerWidth - 32));
  const blocksByPage = $derived.by(() => {
    const map = new Map<number, { index: number; block: ContentListItem }[]>();
    blocks.forEach((block, index) => {
      const page = (block.page_idx ?? 0) + 1;
      map.set(page, [...(map.get(page) ?? []), { index, block }]);
    });
    return map;
  });

  function pageSize(index: number): { width: number; height: number; scale: number } {
    const metric = metrics[index];
    if (!metric) return { width: cssWidth, height: Math.round(cssWidth * 1.3), scale: 1 };
    const scale = (cssWidth / metric.width) * zoom;
    return { width: metric.width * scale, height: metric.height * scale, scale };
  }

  onMount(() => {
    const observer = new ResizeObserver((entries) => {
      const next = Math.floor(entries[0]?.contentRect.width ?? 640);
      if (next > 0) containerWidth = next;
    });
    if (root) observer.observe(root);
    return () => observer.disconnect();
  });

  $effect(() => {
    const source = url;
    let cancelled = false;
    let doc: PDFDocumentProxy | null = null;
    loading = true;
    loadError = '';
    pdf = null;
    pageCount = 0;
    metrics = [];
    void (async () => {
      try {
        doc = await getDocument({ url: source }).promise;
        if (cancelled) {
          await doc.destroy();
          return;
        }
        const count = doc.numPages;
        const nextMetrics: { width: number; height: number }[] = [];
        for (let pageNumber = 1; pageNumber <= count; pageNumber += 1) {
          const page = await doc.getPage(pageNumber);
          const viewport = page.getViewport({ scale: 1 });
          nextMetrics.push({ width: viewport.width, height: viewport.height });
        }
        if (cancelled) {
          await doc.destroy();
          return;
        }
        pdf = doc;
        pageCount = count;
        metrics = nextMetrics;
        untrack(() => onPageChange?.(1, count));
      } catch (caught) {
        if (!cancelled) loadError = caught instanceof Error ? caught.message : 'PDF 无法预览';
      } finally {
        if (!cancelled) loading = false;
      }
    })();
    return () => {
      cancelled = true;
      void doc?.destroy();
    };
  });

  $effect(() => {
    const index = selectedIndex;
    if (index === null || !root) return;
    const page = (blocks[index]?.page_idx ?? 0) + 1;
    void tick().then(() => {
      const target =
        root?.querySelector(`[data-bbox-index="${index}"]`) ??
        root?.querySelector(`[data-page="${page}"]`);
      target?.scrollIntoView({
        block: 'center',
        behavior: prefersReducedMotion() ? 'auto' : 'smooth'
      });
    });
  });

  function onScroll(): void {
    if (!root || !pageCount) return;
    const pages = Array.from(root.querySelectorAll<HTMLElement>('[data-page]'));
    const mid = root.scrollTop + root.clientHeight / 2;
    let current = 1;
    for (const node of pages) {
      const top = node.offsetTop;
      const bottom = top + node.offsetHeight;
      if (mid >= top && mid <= bottom) {
        current = Number(node.dataset.page) || 1;
        break;
      }
    }
    onPageChange?.(current, pageCount);
  }
</script>

<div class="pdf-viewer" bind:this={root} onscroll={onScroll}>
  {#if loading}
    <div class="source-empty"><LoaderCircle class="spin" size={26} /><strong>正在渲染 PDF</strong></div>
  {:else if loadError}
    <div class="source-empty"><CircleAlert size={26} /><strong>无法预览 PDF</strong><span>{loadError}</span></div>
  {:else if pdf}
    {#each metrics as _, index}
      {@const size = pageSize(index)}
      <PdfPage
        {pdf}
        pageNumber={index + 1}
        width={size.width}
        height={size.height}
        scale={size.scale}
        items={blocksByPage.get(index + 1) ?? []}
        {selectedIndex}
        {onSelectBlock}
      />
    {/each}
  {/if}
</div>
