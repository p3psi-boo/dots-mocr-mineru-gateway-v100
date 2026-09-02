<script lang="ts">
  import { onMount } from 'svelte';
  import { bboxStyle, isRenderableBbox } from '$lib/bbox';
  import type { PDFDocumentProxy } from '$lib/pdf';
  import type { RenderTask } from 'pdfjs-dist';
  import type { ContentListItem } from '$lib/types';

  let {
    pdf,
    pageNumber,
    width,
    height,
    scale,
    items,
    selectedIndex,
    onSelectBlock
  }: {
    pdf: PDFDocumentProxy;
    pageNumber: number;
    width: number;
    height: number;
    scale: number;
    items: { index: number; block: ContentListItem }[];
    selectedIndex: number | null;
    onSelectBlock?: (index: number) => void;
  } = $props();

  let host = $state<HTMLDivElement>();
  let canvas = $state<HTMLCanvasElement>();
  let visible = $state(false);

  onMount(() => {
    const root = host?.closest('.pdf-viewer') ?? null;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
      },
      { root, rootMargin: '800px 0px', threshold: 0.01 }
    );
    if (host) observer.observe(host);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (!visible || !pdf || !canvas) return;
    const targetScale = scale;
    const page = pdf;
    const number = pageNumber;
    const node = canvas;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    void (async () => {
      const pdfPage = await page.getPage(number);
      if (cancelled) return;
      const viewport = pdfPage.getViewport({ scale: targetScale });
      const outputScale = Math.min(window.devicePixelRatio || 1, 2);
      node.width = Math.floor(viewport.width * outputScale);
      node.height = Math.floor(viewport.height * outputScale);
      node.style.width = `${viewport.width}px`;
      node.style.height = `${viewport.height}px`;
      const context = node.getContext('2d');
      if (!context) return;
      renderTask = pdfPage.render({
        canvas: node,
        canvasContext: context,
        viewport,
        ...(outputScale === 1 ? {} : { transform: [outputScale, 0, 0, outputScale, 0, 0] })
      });
      await renderTask.promise;
    })();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  });
</script>

<div
  class="pdf-page"
  bind:this={host}
  data-page={pageNumber}
  style={`width:${width}px;height:${height}px`}
>
  {#if visible}
    <canvas bind:this={canvas}></canvas>
    <div class="bbox-layer">
      {#each items as item}
        {#if isRenderableBbox(item.block.bbox)}
          <button
            type="button"
            class="bbox"
            class:selected={selectedIndex === item.index}
            data-bbox-index={item.index}
            style={bboxStyle(item.block.bbox)}
            aria-label={`第 ${pageNumber} 页区块 ${item.index + 1}`}
            aria-pressed={selectedIndex === item.index}
            onclick={() => onSelectBlock?.(item.index)}
          ></button>
        {/if}
      {/each}
    </div>
  {/if}
</div>
