<script lang="ts">
  import { Braces } from '@lucide/svelte';

  let { value, filename }: { value: unknown; filename: string } = $props();
  let expanded = $state(new Set<string>(['$']));

  function entriesOf(node: unknown): [string, unknown][] {
    if (Array.isArray(node)) return node.map((item, index) => [String(index), item]);
    if (node && typeof node === 'object') return Object.entries(node);
    return [];
  }

  function isBranch(node: unknown): boolean {
    return Boolean(node && typeof node === 'object');
  }

  function kindOf(node: unknown): 'array' | 'object' {
    return Array.isArray(node) ? 'array' : 'object';
  }

  function primitive(node: unknown): string {
    if (typeof node === 'string') return JSON.stringify(node);
    if (node === null) return 'null';
    return String(node);
  }

  function valueType(node: unknown): string {
    if (node === null) return 'null';
    return typeof node;
  }

  function toggleBranch(event: Event, path: string): void {
    const next = new Set(expanded);
    if ((event.currentTarget as HTMLDetailsElement).open) next.add(path);
    else next.delete(path);
    expanded = next;
  }
</script>

{#snippet treeNode(key: string, node: unknown, path: string, root = false)}
  {#if isBranch(node)}
    {@const entries = entriesOf(node)}
    {@const kind = kindOf(node)}
    <details class="json-branch" open={expanded.has(path)} ontoggle={(event) => toggleBranch(event, path)}>
      <summary>
        <span class="json-chevron"></span>
        {#if !root}<span class="json-key">{JSON.stringify(key)}</span><span class="json-colon">:</span>{/if}
        <span class="json-bracket">{kind === 'array' ? '[' : '{'}</span>
        <span class="json-count">{entries.length} {kind === 'array' ? '项' : '个字段'}</span>
        <span class="json-preview">{kind === 'array' ? ']' : '}'}</span>
      </summary>
      {#if entries.length && expanded.has(path)}
        <div class="json-children">
          {#each entries as [childKey, childValue]}
            {@render treeNode(childKey, childValue, `${path}/${childKey}`)}
          {/each}
        </div>
      {/if}
      <div class="json-close">{kind === 'array' ? ']' : '}'}</div>
    </details>
  {:else}
    <div class="json-leaf">
      <span class="json-key">{JSON.stringify(key)}</span><span class="json-colon">:</span>
      <span class="json-value json-{valueType(node)}">{primitive(node)}</span>
    </div>
  {/if}
{/snippet}

<div class="json-tree-view">
  <div class="json-label"><Braces size={14} />{filename}</div>
  <div class="json-tree">{@render treeNode('', value, '$', true)}</div>
</div>
