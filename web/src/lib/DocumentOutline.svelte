<script lang="ts">
  import type { OutlineEntry } from '$lib/interactive-markdown';

  let {
    entries,
    selectedIndex = null,
    onJump
  }: {
    entries: OutlineEntry[];
    selectedIndex?: number | null;
    onJump: (index: number) => void;
  } = $props();
</script>

<nav class="outline-rail" aria-label="文档目录">
  <strong>目录</strong>
  {#if entries.length}
    {#each entries as entry (`${entry.page}-${entry.index}-${entry.level}`)}
      <button
        type="button"
        class="outline-item"
        class:page={entry.level === 0}
        class:active={selectedIndex === entry.index}
        style={`--level:${entry.level}`}
        onclick={() => onJump(entry.index)}
      >
        {entry.label}
      </button>
    {/each}
  {:else}
    <p>没有可跳转的标题或页码</p>
  {/if}
</nav>
