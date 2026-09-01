<script lang="ts">
  import { onMount, tick } from 'svelte';
  import {
    ArrowLeft,
    Check,
    ChevronRight,
    CircleAlert,
    Clipboard,
    Clock3,
    Download,
    File as FileIcon,
    FileCheck2,
    FileText,
    Inbox,
    Layers3,
    LoaderCircle,
    PanelLeftClose,
    Pause,
    Play,
    Plus,
    RefreshCw,
    Search,
    Settings2,
    Terminal,
    Trash2,
    Upload,
    X
  } from '@lucide/svelte';
  import InteractiveMarkdown from '$lib/InteractiveMarkdown.svelte';
  import JsonTree from '$lib/JsonTree.svelte';
  import { getHealth, getServiceLogs, getTask, getTaskResult, submitTask } from '$lib/api';
  import { copyTextCompat, downloadBlob, safeDownloadName } from '$lib/interactive-markdown';
  import { loadFile, loadResult, loadTasks, saveFiles, saveResult, saveTasks } from '$lib/storage';
  import type {
    FileResult,
    HealthStatus,
    ServiceLogEntry,
    SubmitOptions,
    TaskRecord,
    TaskResult,
    TaskState,
    TaskStatus
  } from '$lib/types';

  type View = 'new' | 'tasks' | 'logs' | 'detail';
  type ResultTab = 'markdown' | 'json';

  const terminalStates: TaskState[] = ['completed', 'failed', 'expired'];
  const acceptedExtensions = '.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff';
  const defaultOptions: SubmitOptions = {
    lang: 'ch',
    parseMethod: 'auto',
    formula: true,
    table: true,
    images: true,
    startPage: 0,
    endPage: 63
  };

  let view = $state<View>('new');
  let tasks = $state<TaskRecord[]>([]);
  let health = $state<HealthStatus | null>(null);
  let files = $state<File[]>([]);
  let options = $state<SubmitOptions>({ ...defaultOptions });
  let settingsOpen = $state(false);
  let dragging = $state(false);
  let submitting = $state(false);
  let refreshing = $state(false);
  let error = $state('');
  let selectedTaskId = $state('');
  let selectedFileIndex = $state(0);
  let result = $state<TaskResult | null>(null);
  let resultLoading = $state(false);
  let resultTab = $state<ResultTab>('markdown');
  let originalFile = $state<File | null>(null);
  let originalUrl = $state('');
  let copied = $state(false);
  let fileInput = $state<HTMLInputElement>();
  let serviceLogs = $state<ServiceLogEntry[]>([]);
  let logInstanceId = $state('');
  let logCursor = $state(0);
  let logsLoading = $state(false);
  let logsPaused = $state(false);
  let logLevel = $state<'all' | ServiceLogEntry['level']>('all');
  let logQuery = $state('');
  let logViewport = $state<HTMLDivElement>();

  const activeTasks = $derived(tasks.filter((task) => !terminalStates.includes(task.status)));
  const completedTasks = $derived(tasks.filter((task) => task.status === 'completed'));
  const selectedTask = $derived(tasks.find((task) => task.task_id === selectedTaskId) ?? null);
  const artifactNames = $derived(result ? Object.keys(result.results) : selectedTask?.file_names ?? []);
  const selectedArtifactName = $derived(artifactNames[selectedFileIndex] ?? artifactNames[0] ?? '');
  const selectedArtifact = $derived(
    result && selectedArtifactName ? result.results[selectedArtifactName] : undefined
  );
  const visibleTasks = $derived(
    [...tasks].sort(
      (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    )
  );
  const visibleLogs = $derived(
    serviceLogs.filter((entry) => {
      if (logLevel !== 'all' && entry.level !== logLevel) return false;
      const query = logQuery.trim().toLocaleLowerCase();
      if (!query) return true;
      return `${entry.source} ${entry.message} ${JSON.stringify(entry.context)}`
        .toLocaleLowerCase()
        .includes(query);
    })
  );
  const prettyJson = $derived(
    JSON.stringify(expandArtifact(selectedArtifact), null, 2)
  );

  function mergeStatus(record: TaskRecord, status: TaskStatus): TaskRecord {
    return { ...record, ...status, original_names: record.original_names, sizes: record.sizes };
  }

  function expandArtifact(artifact?: FileResult): Record<string, unknown> {
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

  function persist(next: TaskRecord[]): void {
    tasks = next;
    saveTasks(next);
  }

  function updateRoute(nextView: View, taskId = '', replace = false): void {
    view = nextView;
    selectedTaskId = taskId;
    const url = new URL(window.location.href);
    url.search = '';
    if (nextView === 'tasks') url.searchParams.set('view', 'tasks');
    if (nextView === 'logs') url.searchParams.set('view', 'logs');
    if (nextView === 'detail') url.searchParams.set('task', taskId);
    history[replace ? 'replaceState' : 'pushState']({}, '', url);
  }

  async function readRoute(): Promise<void> {
    const url = new URL(window.location.href);
    const taskId = url.searchParams.get('task');
    if (taskId) {
      view = 'detail';
      selectedTaskId = taskId;
      selectedFileIndex = 0;
      await ensureTask(taskId);
      await loadSelectedTask();
    } else {
      const requestedView = url.searchParams.get('view');
      view = requestedView === 'tasks' || requestedView === 'logs' ? requestedView : 'new';
      selectedTaskId = '';
      if (view === 'logs') await refreshLogs(true);
    }
  }

  async function ensureTask(taskId: string): Promise<void> {
    if (tasks.some((task) => task.task_id === taskId)) return;
    try {
      const status = await getTask(taskId);
      persist([
        {
          ...status,
          original_names: status.file_names,
          sizes: status.file_names.map(() => 0)
        },
        ...tasks
      ]);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : '任务不存在';
    }
  }

  async function refreshHealth(): Promise<void> {
    try {
      health = await getHealth();
    } catch {
      health = null;
    }
  }

  async function refreshTasks(): Promise<void> {
    if (refreshing || activeTasks.length === 0) return;
    refreshing = true;
    const updated = await Promise.all(
      tasks.map(async (record) => {
        if (terminalStates.includes(record.status)) return record;
        try {
          const status = await getTask(record.task_id);
          if (status.status === 'completed') {
            const taskResult = await getTaskResult(record.task_id);
            await saveResult(record.task_id, taskResult);
            if (selectedTaskId === record.task_id) result = taskResult;
          }
          return mergeStatus(record, status);
        } catch (caught) {
          const message = caught instanceof Error ? caught.message : '';
          return message.includes('404') || message.includes('not found')
            ? { ...record, status: 'expired' as const, error: '任务已过期或服务已重启' }
            : record;
        }
      })
    );
    persist(updated);
    refreshing = false;
  }

  async function refreshLogs(reset = false): Promise<void> {
    if (logsLoading || (logsPaused && !reset)) return;
    logsLoading = true;
    try {
      const response = await getServiceLogs(reset ? 0 : logCursor, reset ? 300 : 200);
      const restarted = logInstanceId !== '' && logInstanceId !== response.instance_id;
      if (reset || restarted) serviceLogs = response.items;
      else if (response.items.length) {
        const known = new Set(serviceLogs.map((entry) => entry.sequence));
        serviceLogs = [...serviceLogs, ...response.items.filter((entry) => !known.has(entry.sequence))]
          .slice(-response.capacity);
      }
      logInstanceId = response.instance_id;
      logCursor = response.items.at(-1)?.sequence ?? response.latest_sequence;
      await tick();
      if (logViewport && !logsPaused) logViewport.scrollTop = logViewport.scrollHeight;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : '日志读取失败';
    } finally {
      logsLoading = false;
    }
  }

  async function refresh(): Promise<void> {
    await Promise.all([
      refreshHealth(),
      refreshTasks(),
      view === 'logs' ? refreshLogs() : Promise.resolve()
    ]);
  }

  function addFiles(nextFiles: File[]): void {
    error = '';
    const supported = nextFiles.filter((file) =>
      /\.(pdf|png|jpe?g|webp|bmp|tiff?)$/i.test(file.name)
    );
    const merged = [...files, ...supported].slice(0, 8);
    files = merged.filter(
      (file, index) => merged.findIndex((other) => other.name === file.name && other.size === file.size) === index
    );
    if (supported.length !== nextFiles.length) error = '已忽略不支持的文件格式';
  }

  function onFileChange(event: Event): void {
    const target = event.currentTarget as HTMLInputElement;
    addFiles(Array.from(target.files ?? []));
    target.value = '';
  }

  function onDrop(event: DragEvent): void {
    event.preventDefault();
    dragging = false;
    addFiles(Array.from(event.dataTransfer?.files ?? []));
  }

  function removeFile(index: number): void {
    files = files.filter((_, fileIndex) => fileIndex !== index);
  }

  async function createTask(): Promise<void> {
    if (files.length === 0 || submitting) return;
    submitting = true;
    error = '';
    try {
      const submittedFiles = [...files];
      const status = await submitTask(submittedFiles, options);
      const record: TaskRecord = {
        ...status,
        original_names: submittedFiles.map((file) => file.name),
        sizes: submittedFiles.map((file) => file.size)
      };
      await saveFiles(status.task_id, submittedFiles);
      persist([record, ...tasks.filter((task) => task.task_id !== record.task_id)]);
      files = [];
      await openTask(record.task_id);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : '提交失败';
    } finally {
      submitting = false;
    }
  }

  async function openTask(taskId: string): Promise<void> {
    updateRoute('detail', taskId);
    selectedFileIndex = 0;
    resultTab = 'markdown';
    error = '';
    await loadSelectedTask();
  }

  async function loadSelectedTask(): Promise<void> {
    if (!selectedTaskId) return;
    resultLoading = true;
    result = (await loadResult(selectedTaskId)) ?? null;
    if (!result && selectedTask?.status === 'completed') {
      try {
        result = await getTaskResult(selectedTaskId);
        await saveResult(selectedTaskId, result);
      } catch (caught) {
        error = caught instanceof Error ? caught.message : '结果读取失败';
      }
    }
    await loadOriginal(selectedTaskId, selectedFileIndex);
    resultLoading = false;
  }

  async function selectFile(index: number): Promise<void> {
    selectedFileIndex = index;
    if (selectedTaskId) await loadOriginal(selectedTaskId, index);
  }

  async function loadOriginal(taskId: string, index: number): Promise<void> {
    if (originalUrl) URL.revokeObjectURL(originalUrl);
    originalFile = (await loadFile(taskId, index)) ?? null;
    originalUrl = originalFile ? URL.createObjectURL(originalFile) : '';
  }

  async function copyResult(): Promise<void> {
    const content = resultTab === 'markdown' ? selectedArtifact?.md_content ?? '' : prettyJson;
    copied = await copyTextCompat(content);
    window.setTimeout(() => (copied = false), 1600);
  }

  function minimalPdfUrl(url: string): string {
    return url ? `${url}#toolbar=0&navpanes=0&scrollbar=1&view=FitH` : '';
  }

  function exportMarkdown(): void {
    if (!selectedArtifact?.md_content) return;
    downloadBlob(
      selectedArtifact.md_content,
      'text/markdown;charset=utf-8',
      safeDownloadName(selectedArtifactName, 'md')
    );
  }

  function formatDate(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).format(new Date(value));
  }

  function formatSize(bytes: number): string {
    if (!bytes) return '—';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function formatLogTime(value: string): string {
    return new Intl.DateTimeFormat('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
      hour12: false
    }).format(new Date(value));
  }

  function contextEntries(context: Record<string, unknown>): [string, string][] {
    return Object.entries(context)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => [key, typeof value === 'string' ? value : JSON.stringify(value)]);
  }

  function statusText(status: TaskState): string {
    return {
      pending: '排队中',
      processing: '解析中',
      completed: '已完成',
      failed: '失败',
      expired: '已过期'
    }[status];
  }

  onMount(() => {
    tasks = loadTasks();
    void readRoute();
    void refresh();
    const poller = window.setInterval(() => void refresh(), 2500);
    const onPopState = () => void readRoute();
    window.addEventListener('popstate', onPopState);
    return () => {
      window.clearInterval(poller);
      window.removeEventListener('popstate', onPopState);
      if (originalUrl) URL.revokeObjectURL(originalUrl);
    };
  });
</script>

<svelte:head>
  <title>dots.mocr · 文档解析</title>
</svelte:head>

<div class="shell" class:detail-mode={view === 'detail'}>
  <aside class="sidebar">
    <button class="brand" onclick={() => updateRoute('new')} aria-label="返回新解析">
      <span class="brand-mark"><span></span><span></span><span></span></span>
      <strong>dots.mocr</strong>
    </button>

    <nav aria-label="主导航">
      <button class:active={view === 'new'} onclick={() => updateRoute('new')}>
        <Plus size={18} strokeWidth={1.8} />
        <span>新解析</span>
      </button>
      <button class:active={view === 'tasks'} onclick={() => updateRoute('tasks')}>
        <Layers3 size={18} strokeWidth={1.8} />
        <span>任务</span>
        {#if activeTasks.length}<em>{activeTasks.length}</em>{/if}
      </button>
      <button class:active={view === 'logs'} onclick={() => { updateRoute('logs'); void refreshLogs(true); }}>
        <Terminal size={18} strokeWidth={1.8} />
        <span>日志</span>
      </button>
    </nav>

    <div class="recent-label">最近完成</div>
    <div class="recent-list">
      {#each completedTasks.slice(0, 5) as task (task.task_id)}
        <button onclick={() => openTask(task.task_id)} title={task.original_names.join('、')}>
          <FileCheck2 size={14} />
          <span>{task.original_names[0] ?? task.file_names[0]}</span>
        </button>
      {:else}
        <p>暂无记录</p>
      {/each}
    </div>

    <div class="service-chip" class:offline={!health}>
      <span class="signal"></span>
      <div>
        <strong>{health ? '服务在线' : '连接中断'}</strong>
        {#if health}
          <small class="service-metrics">
            <span><b>后端</b><em>{health.model_backend}</em></span>
            <span><b>队列</b><em>{health.queued_tasks}</em></span>
            <span><b>解析中</b><em>{health.processing_tasks}</em></span>
          </small>
        {:else}
          <small>等待 API 响应</small>
        {/if}
      </div>
    </div>
  </aside>

  <main>
    {#if view === 'new'}
      <section class="new-view">
        <div class="new-content">
          <div
            class="dropzone"
            role="group"
            aria-label="文件上传区域"
            class:dragging
            class:has-files={files.length > 0}
            ondragover={(event) => { event.preventDefault(); dragging = true; }}
            ondragleave={() => (dragging = false)}
            ondrop={onDrop}
          >
            <button class="settings-button" onclick={() => (settingsOpen = !settingsOpen)} aria-label="解析设置">
              <Settings2 size={16} />
            </button>

            {#if files.length === 0}
              <button class="drop-empty" onclick={() => fileInput?.click()}>
                <span class="drop-icon"><Upload size={22} strokeWidth={1.8} /></span>
                <strong>拖入文件，或点击选择</strong>
                <small>PDF · PNG · JPG · WEBP · TIFF，最多 8 个</small>
              </button>
            {:else}
              <div class="file-selection">
                <div class="file-list">
                  {#each files as file, index (`${file.name}-${file.size}`)}
                    <div class="file-row">
                      <span class="file-kind">{file.name.split('.').pop()?.slice(0, 4).toUpperCase()}</span>
                      <div><strong>{file.name}</strong><small>{formatSize(file.size)}</small></div>
                      <button onclick={() => removeFile(index)} aria-label={`移除 ${file.name}`}><X size={15} /></button>
                    </div>
                  {/each}
                </div>
                <div class="selection-actions">
                  <button class="ghost" onclick={() => fileInput?.click()}><Plus size={15} />继续添加</button>
                  <button class="primary" disabled={submitting} onclick={createTask}>
                    {#if submitting}<LoaderCircle class="spin" size={16} />提交中{:else}开始解析{/if}
                  </button>
                </div>
              </div>
            {/if}

            <input bind:this={fileInput} class="visually-hidden" type="file" multiple accept={acceptedExtensions} onchange={onFileChange} />

            {#if settingsOpen}
              <div class="settings-panel">
                <div class="settings-title"><span>解析参数</span><button onclick={() => (settingsOpen = false)} aria-label="关闭"><X size={15} /></button></div>
                <label>解析方式
                  <select bind:value={options.parseMethod}>
                    <option value="auto">自动判断</option>
                    <option value="ocr">强制 OCR</option>
                    <option value="txt">文本优先</option>
                  </select>
                </label>
                <label>文档语言
                  <select bind:value={options.lang}>
                    <option value="ch">中文 / 混合</option>
                    <option value="en">英文</option>
                  </select>
                </label>
                <div class="page-range">
                  <label>起始页<input type="number" min="0" bind:value={options.startPage} /></label>
                  <label>结束页<input type="number" min={options.startPage} bind:value={options.endPage} /></label>
                </div>
                <label class="toggle"><span>公式识别</span><input type="checkbox" bind:checked={options.formula} /><i></i></label>
                <label class="toggle"><span>表格识别</span><input type="checkbox" bind:checked={options.table} /><i></i></label>
                <label class="toggle"><span>图片区域</span><input type="checkbox" bind:checked={options.images} /><i></i></label>
              </div>
            {/if}
          </div>

          {#if error}<div class="inline-error"><CircleAlert size={15} />{error}</div>{/if}
        </div>
      </section>
    {:else if view === 'tasks'}
      <section class="tasks-view">
        <header class="page-head">
          <div>
            <h1>任务</h1>
            <p>{activeTasks.length} 进行中 · {completedTasks.length} 已完成</p>
          </div>
          <div class="head-actions">
            <button class="ghost refresh" class:spinning={refreshing} onclick={refresh} aria-label="刷新"><RefreshCw size={15} /></button>
            <button class="primary compact" onclick={() => updateRoute('new')}><Plus size={16} />新解析</button>
          </div>
        </header>

        <div class="task-table">
          {#each visibleTasks as task (task.task_id)}
            <button class="task-row" onclick={() => openTask(task.task_id)}>
              <span class="task-file">
                <i><FileText size={17} /></i>
                <span><strong>{task.original_names[0] ?? task.file_names[0]}</strong><small>{task.original_names.length > 1 ? `${task.original_names.length} 个文件 · ` : ''}{formatDate(task.created_at)} · {formatSize(task.sizes.reduce((sum, size) => sum + size, 0))}</small></span>
              </span>
              <span class="task-status">
                <i class={`status ${task.status}`}><b></b>{statusText(task.status)}</i>
                {#if task.queued_ahead}<small class="queued">前方 {task.queued_ahead} 项</small>{/if}
              </span>
              <span class="row-arrow"><ChevronRight size={16} /></span>
            </button>
          {:else}
            <div class="empty-tasks"><Inbox size={28} /><strong>还没有任务</strong><span>上传文档后会出现在这里</span></div>
          {/each}
        </div>
      </section>
    {:else if view === 'logs'}
      <section class="logs-view">
        <header class="page-head">
          <div>
            <h1>日志</h1>
            <p class="log-status" class:offline={!health}><i></i>{health ? '服务正常，实时轮询中' : '服务不可达'}</p>
          </div>
          <div class="head-actions">
            <button class="ghost refresh" class:spinning={logsLoading} onclick={() => refreshLogs(true)} aria-label="刷新"><RefreshCw size={15} /></button>
          </div>
        </header>

        <div class="log-console">
          <div class="log-toolbar">
            <div class="level-filter" aria-label="日志级别">
              {#each ['all', 'info', 'warning', 'error'] as level}
                <button class:active={logLevel === level} onclick={() => (logLevel = level as typeof logLevel)}>{level}</button>
              {/each}
            </div>
            <label class="log-search">
              <Search size={14} strokeWidth={2} />
              <input bind:value={logQuery} placeholder="筛选任务 ID、来源或消息" aria-label="筛选日志" />
            </label>
            <button class="log-action" onclick={() => (logsPaused = !logsPaused)}>
              {#if logsPaused}<Play size={14} strokeWidth={2} />继续{:else}<Pause size={14} strokeWidth={2} />暂停{/if}
            </button>
            <button class="log-action" onclick={() => (serviceLogs = [])}><Trash2 size={14} strokeWidth={2} />清空</button>
          </div>

          <div class="log-stream" bind:this={logViewport}>
            {#each visibleLogs as entry (entry.sequence)}
              <article class={`log-entry ${entry.level}`}>
                <time>{formatLogTime(entry.timestamp)}</time>
                <span class="log-level">{entry.level}</span>
                <span class="log-source">{entry.source}</span>
                <div class="log-message">
                  <strong>{entry.message}</strong>
                  {#if contextEntries(entry.context).length}
                    <div class="log-context">
                      {#each contextEntries(entry.context) as [key, value]}
                        <span><b>{key}</b>={value}</span>
                      {/each}
                    </div>
                  {/if}
                </div>
              </article>
            {:else}
              <div class="empty-log"><Terminal size={26} /><strong>{logsLoading ? '正在连接日志流' : '没有匹配的日志'}</strong></div>
            {/each}
          </div>
        </div>
      </section>
    {:else}
      <section class="detail-view">
        <header class="detail-header">
          <button class="back" onclick={() => updateRoute('tasks')} aria-label="返回任务列表"><ArrowLeft size={17} /></button>
          <div class="detail-title"><strong>{selectedTask?.original_names[0] ?? selectedTask?.file_names[0] ?? '解析任务'}</strong></div>
          {#if selectedTask}<i class={`status ${selectedTask.status}`}><b></b>{statusText(selectedTask.status)}</i>{/if}
          <div class="detail-spacer"></div>
          {#if artifactNames.length > 1}
            <select class="file-switcher" value={selectedFileIndex} onchange={(event) => selectFile(Number((event.currentTarget as HTMLSelectElement).value))}>
              {#each artifactNames as name, index}<option value={index}>{name}</option>{/each}
            </select>
          {/if}
        </header>

        <div class="viewer">
          <section class="source-pane">
            <div class="pane-bar"><span>原文件</span><small>{originalFile ? formatSize(originalFile.size) : '仅保存在当前浏览器'}</small></div>
            <div class="source-stage">
              {#if originalUrl && originalFile?.type === 'application/pdf'}
                <iframe src={minimalPdfUrl(originalUrl)} title="原始 PDF（精简视图）"></iframe>
              {:else if originalUrl}
                <img src={originalUrl} alt={originalFile?.name ?? '原始文档'} />
              {:else}
                <div class="source-empty"><FileIcon size={32} /><strong>原文件不可用</strong><span>此任务不是在当前浏览器提交，或浏览器存储已清理。</span></div>
              {/if}
            </div>
          </section>

          <section class="result-pane">
            <div class="pane-bar result-bar">
              <div class="result-tabs">
                <button class:active={resultTab === 'markdown'} onclick={() => (resultTab = 'markdown')}>Markdown</button>
                <button class:active={resultTab === 'json'} onclick={() => (resultTab = 'json')}>JSON</button>
              </div>
              <div class="result-actions">
                <button class="copy" disabled={!selectedArtifact?.md_content} onclick={exportMarkdown} title="下载 Markdown 文件">
                  <Download size={15} />
                  导出 Markdown
                </button>
                <button class="copy" disabled={!selectedArtifact} onclick={copyResult}>
                  <span class="copy-icons" class:copied>
                    <Clipboard size={15} class="icon-clip" />
                    <Check size={15} class="icon-check" />
                  </span>
                  {copied ? '已复制' : '复制'}
                </button>
              </div>
            </div>
            <div class="result-scroll">
              {#if resultLoading}
                <div class="result-state"><LoaderCircle class="spin" size={26} /><strong>正在读取结果</strong></div>
              {:else if selectedTask?.status === 'pending'}
                <div class="result-state"><Clock3 size={28} /><strong>排队中</strong><span>前方还有 {selectedTask.queued_ahead ?? 0} 项任务</span></div>
              {:else if selectedTask?.status === 'processing'}
                <div class="result-state processing-art"><span class="scanner"></span><LoaderCircle class="spin" size={28} /><strong>正在解析</strong><span>完成后会自动显示结果</span></div>
              {:else if selectedTask?.status === 'failed' || selectedTask?.status === 'expired'}
                <div class="result-state failed-art"><CircleAlert size={28} /><strong>{statusText(selectedTask.status)}</strong><span>{selectedTask.error}</span></div>
              {:else if selectedArtifact && resultTab === 'markdown'}
                {#key selectedArtifactName}
                  <InteractiveMarkdown artifact={selectedArtifact} filename={selectedArtifactName} />
                {/key}
              {:else if selectedArtifact && resultTab === 'json'}
                <JsonTree value={expandArtifact(selectedArtifact)} filename={`${selectedArtifactName}.json`} />
              {:else}
                <div class="result-state"><PanelLeftClose size={28} /><strong>等待解析结果</strong></div>
              {/if}
            </div>
          </section>
        </div>
      </section>
    {/if}
  </main>
</div>
