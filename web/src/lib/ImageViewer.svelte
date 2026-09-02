<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { bboxStyle, isRenderableBbox, prefersReducedMotion } from '$lib/bbox';
  import type { ContentListItem } from '$lib/types';

  let {
    url,
    alt,
    blocks = [],
    selectedIndex = null,
    fit = 'contain',
    zoom = 1,
    onSelectBlock
  }: {
    url: string;
    alt: string;
    blocks?: ContentListItem[];
    selectedIndex?: number | null;
    fit?: 'contain' | 'width' | 'actual';
    zoom?: number;
    onSelectBlock?: (index: number) => void;
  } = $props();

  let root = $state<HTMLDivElement>();
  let naturalWidth = $state(0);
  let naturalHeight = $state(0);
  let stageWidth = $state(0);
  let stageHeight = $state(0);

  const display = $derived.by(() => {
    if (!naturalWidth || !naturalHeight) return { width: 0, height: 0 };
    const pad = 40;
    const availableWidth = Math.max(120, stageWidth - pad);
    const availableHeight = Math.max(120, stageHeight - pad);
    let scale = zoom;
    if (fit === 'contain') {
      scale = Math.min(availableWidth / naturalWidth, availableHeight / naturalHeight) * zoom;
    } else if (fit === 'width') {
      scale = (availableWidth / naturalWidth) * zoom;
    }
    return { width: naturalWidth * scale, height: naturalHeight * scale };
  });

  onMount(() => {
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      stageWidth = rect.width;
      stageHeight = rect.height;
    });
    if (root) observer.observe(root);
    return () => observer.disconnect();
  });

  function onLoad(event: Event): void {
    const image = event.currentTarget as HTMLImageElement;
    naturalWidth = image.naturalWidth;
    naturalHeight = image.naturalHeight;
  }

  $effect(() => {
    const index = selectedIndex;
    if (index === null || !root) return;
    void tick().then(() => {
      root
        ?.querySelector(`[data-bbox-index="${index}"]`)
        ?.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
    });
  });
</script>

<div class="image-viewer" class:contain={fit === 'contain'} bind:this={root}>
  <div
    class="image-stack"
    style={display.width ? `width:${display.width}px;height:${display.height}px` : ''}
  >
    <img src={url} {alt} onload={onLoad} />
    <div class="bbox-layer">
      {#each blocks as block, index}
        {#if isRenderableBbox(block.bbox)}
          <button
            type="button"
            class="bbox"
            class:selected={selectedIndex === index}
            data-bbox-index={index}
            style={bboxStyle(block.bbox)}
            aria-label={`图片区块 ${index + 1}`}
            aria-pressed={selectedIndex === index}
            onclick={() => onSelectBlock?.(index)}
          ></button>
        {/if}
      {/each}
    </div>
  </div>
</div>
