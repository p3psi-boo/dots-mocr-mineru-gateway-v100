<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Braces,
    Check,
    ChevronDown,
    Clipboard,
    Download,
    ExternalLink,
    KeyRound,
    LoaderCircle,
    Search
  } from '@lucide/svelte';
  import { getOpenApiDocument } from '$lib/api';
  import { copyTextCompat, downloadBlob } from '$lib/interactive-markdown';
  import type { OpenApiDocument, OpenApiOperation, OpenApiSchema } from '$lib/types';

  type OperationView = { method: string; path: string; operation: OpenApiOperation; key: string };
  type OperationGroup = { tag: string; description: string; operations: OperationView[] };

  const httpMethods = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'];

  let spec = $state<OpenApiDocument | null>(null);
  let loading = $state(true);
  let loadError = $state('');
  let query = $state('');
  let activeOperation = $state('');
  let copiedOperation = $state('');

  const operations = $derived.by(() => {
    if (!spec) return [] as OperationView[];
    const result: OperationView[] = [];
    for (const [path, pathItem] of Object.entries(spec.paths)) {
      for (const method of httpMethods) {
        const operation = pathItem[method];
        if (!operation || typeof operation !== 'object') continue;
        result.push({ method, path, operation: operation as OpenApiOperation, key: `${method}:${path}` });
      }
    }
    return result;
  });

  const groups = $derived.by(() => {
    const needle = query.trim().toLocaleLowerCase();
    const filtered = operations.filter(({ method, path, operation }) =>
      !needle || `${method} ${path} ${operation.summary ?? ''} ${operation.description ?? ''}`
        .toLocaleLowerCase()
        .includes(needle)
    );
    const grouped = new Map<string, OperationView[]>();
    for (const operation of filtered) {
      const tag = operation.operation.tags?.[0] ?? 'Other';
      grouped.set(tag, [...(grouped.get(tag) ?? []), operation]);
    }
    return Array.from(grouped, ([tag, taggedOperations]): OperationGroup => ({
      tag,
      description: spec?.tags?.find((item) => item.name === tag)?.description ?? '',
      operations: taggedOperations
    }));
  });

  const schemas = $derived(Object.entries(spec?.components?.schemas ?? {}));
  const endpointCount = $derived(operations.length);

  onMount(() => {
    const controller = new AbortController();
    void loadSpec(controller.signal);
    return () => controller.abort();
  });

  async function loadSpec(signal?: AbortSignal): Promise<void> {
    loading = true;
    loadError = '';
    try {
      spec = await getOpenApiDocument(signal);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return;
      loadError = caught instanceof Error ? caught.message : 'OpenAPI 文档读取失败';
    } finally {
      loading = false;
    }
  }

  function toggleOperation(key: string): void {
    activeOperation = activeOperation === key ? '' : key;
  }

  function schemaLabel(schema?: OpenApiSchema): string {
    if (!schema) return '任意类型';
    if (schema.$ref) return schema.$ref.split('/').pop() ?? schema.$ref;
    if (schema.enum?.length) return schema.enum.map(String).join(' | ');
    if (schema.type === 'array') return `array<${schemaLabel(schema.items)}>`;
    const compound = schema.oneOf ?? schema.anyOf ?? schema.allOf;
    if (compound?.length) return compound.map(schemaLabel).join(' | ');
    return [schema.type ?? 'object', schema.format].filter(Boolean).join(' · ');
  }

  function requestContent(operation: OpenApiOperation): [string, { schema?: OpenApiSchema }][] {
    return Object.entries(operation.requestBody?.content ?? {});
  }

  function responseEntries(operation: OpenApiOperation): [string, { description?: string }][] {
    return Object.entries(operation.responses ?? {});
  }

  function securityNames(operation: OpenApiOperation): string[] {
    return (operation.security ?? []).flatMap((item) => Object.keys(item));
  }

  async function copyEndpoint(view: OperationView): Promise<void> {
    const copied = await copyTextCompat(`${view.method.toUpperCase()} ${location.origin}${view.path}`);
    if (!copied) return;
    copiedOperation = view.key;
    window.setTimeout(() => (copiedOperation = ''), 1400);
  }

  function downloadSpec(): void {
    if (!spec) return;
    downloadBlob(JSON.stringify(spec, null, 2), 'application/json;charset=utf-8', 'openapi.json');
  }
</script>

<section class="api-view">
  <header class="page-head api-page-head">
    <div>
      <h1>API 文档</h1>
      <p>{spec ? `OpenAPI ${spec.openapi} · ${endpointCount} 个端点` : '读取接口定义与数据模型'}</p>
    </div>
    <div class="head-actions">
      <a class="ghost api-link-button" href="/openapi.json" target="_blank" rel="noreferrer"><ExternalLink size={15} />原始 JSON</a>
      <button class="primary compact" disabled={!spec} onclick={downloadSpec}><Download size={15} />下载文档</button>
    </div>
  </header>

  {#if loading}
    <div class="api-state"><LoaderCircle class="spin" size={24} /><strong>正在读取 OpenAPI 文档</strong></div>
  {:else if loadError}
    <div class="api-state api-state-error"><Braces size={24} /><strong>{loadError}</strong><button class="ghost" onclick={() => loadSpec()}>重新加载</button></div>
  {:else if spec}
    <div class="api-workspace">
      <aside class="api-toc">
        <label class="api-search">
          <Search size={14} />
          <input id="api-search-input" bind:value={query} placeholder="搜索端点" aria-label="搜索 API 端点" />
        </label>
        <div class="api-toc-label">接口分组</div>
        {#each groups as group}
          <a href={`#api-${group.tag.replaceAll(' ', '-').toLowerCase()}`}>
            <span>{group.tag}</span><em>{group.operations.length}</em>
          </a>
        {/each}
        {#if schemas.length}
          <a href="#api-schemas"><span>数据模型</span><em>{schemas.length}</em></a>
        {/if}
      </aside>

      <div class="api-document">
        <section class="api-intro">
          <span class="api-version">v{spec.info.version}</span>
          <div>
            <h2>{spec.info.title}</h2>
            <p>{spec.info.description ?? spec.info.summary}</p>
          </div>
        </section>

        {#each groups as group}
          <section class="api-group" id={`api-${group.tag.replaceAll(' ', '-').toLowerCase()}`}>
            <div class="api-group-heading">
              <div><h2>{group.tag}</h2>{#if group.description}<p>{group.description}</p>{/if}</div>
              <span>{group.operations.length} 个端点</span>
            </div>

            <div class="api-operation-list">
              {#each group.operations as view (view.key)}
                {@const operation = view.operation}
                {@const expanded = activeOperation === view.key}
                <article class="api-operation" class:expanded data-method={view.method}>
                  <button class="api-operation-trigger" onclick={() => toggleOperation(view.key)} aria-expanded={expanded}>
                    <code class="api-method">{view.method}</code>
                    <code class="api-path">{view.path}</code>
                    <span>{operation.summary ?? operation.operationId ?? '未命名端点'}</span>
                    <ChevronDown size={16} />
                  </button>

                  {#if expanded}
                    <div class="api-operation-body">
                      <div class="api-operation-topline">
                        <p>{operation.description ?? operation.summary}</p>
                        <button class="api-copy-endpoint" onclick={() => copyEndpoint(view)}>
                          {#if copiedOperation === view.key}<Check size={14} />已复制{:else}<Clipboard size={14} />复制地址{/if}
                        </button>
                      </div>

                      {#if securityNames(operation).length}
                        <div class="api-auth"><KeyRound size={14} /><strong>认证</strong><span>{securityNames(operation).join('、')}</span></div>
                      {/if}

                      {#if operation.parameters?.length}
                        <div class="api-detail-section">
                          <h3>参数</h3>
                          <div class="api-param-table">
                            {#each operation.parameters as parameter}
                              <div class="api-param-row">
                                <code>{parameter.name}</code>
                                <span>{parameter.in}</span>
                                <b>{schemaLabel(parameter.schema)}</b>
                                <p>{parameter.description ?? (parameter.required ? '必填' : '可选')}</p>
                                {#if parameter.required}<em>必填</em>{/if}
                              </div>
                            {/each}
                          </div>
                        </div>
                      {/if}

                      {#if requestContent(operation).length}
                        <div class="api-detail-section">
                          <h3>请求体 {#if operation.requestBody?.required}<em>必填</em>{/if}</h3>
                          <div class="api-content-types">
                            {#each requestContent(operation) as [contentType, media]}
                              <span><code>{contentType}</code><b>{schemaLabel(media.schema)}</b></span>
                            {/each}
                          </div>
                        </div>
                      {/if}

                      {#if responseEntries(operation).length}
                        <div class="api-detail-section">
                          <h3>响应</h3>
                          <div class="api-responses">
                            {#each responseEntries(operation) as [status, response]}
                              <span class:success={status.startsWith('2')}><code>{status}</code><p>{response.description ?? 'Response'}</p></span>
                            {/each}
                          </div>
                        </div>
                      {/if}
                    </div>
                  {/if}
                </article>
              {/each}
            </div>
          </section>
        {:else}
          <div class="api-no-results">没有匹配的 API 端点</div>
        {/each}

        {#if schemas.length && !query}
          <section class="api-group" id="api-schemas">
            <div class="api-group-heading"><div><h2>数据模型</h2><p>OpenAPI components 中定义的复用结构。</p></div><span>{schemas.length} 个模型</span></div>
            <div class="api-schema-list">
              {#each schemas as [name, schema]}
                <details class="api-schema">
                  <summary><Braces size={15} /><strong>{name}</strong><code>{schemaLabel(schema)}</code><ChevronDown size={15} /></summary>
                  <div class="api-schema-body">
                    {#if schema.description}<p>{schema.description}</p>{/if}
                    {#if schema.properties}
                      {#each Object.entries(schema.properties) as [property, propertySchema]}
                        <div class="api-schema-property">
                          <code>{property}</code><b>{schemaLabel(propertySchema)}</b>
                          <span>{propertySchema.description ?? (schema.required?.includes(property) ? '必填' : '可选')}</span>
                        </div>
                      {/each}
                    {:else}
                      <div class="api-schema-property"><code>value</code><b>{schemaLabel(schema)}</b></div>
                    {/if}
                  </div>
                </details>
              {/each}
            </div>
          </section>
        {/if}
      </div>
    </div>
  {/if}
</section>
