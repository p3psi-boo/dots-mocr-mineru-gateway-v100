<script lang="ts">
  import { onMount, tick } from 'svelte';
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';
  import {
    ArrowLeft,
    Check,
    ChevronRight,
    CircleAlert,
    Clipboard,
    Clock3,
    Code2,
    File as FileIcon,
    FileCheck2,
    FileClock,
    FileText,
    Gauge,
    Image as ImageIcon,
    Inbox,
    Layers3,
    LoaderCircle,
    PanelLeftClose,
    Pause,
    Play,
    Plus,
    RefreshCw,
    Settings2,
    Sparkles,
    Terminal,
    Upload,
    X
  } from '@lucide/svelte';
  import { getHealth, getServiceLogs, getTask, getTaskResult, submitTask } from '$lib/api';
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
  const markdownHtml = $derived.by(() => {
    const artifact = selectedArtifact;
    const source = (artifact?.md_content ?? '').replace(
      /!\[([^\]]*)\]\(images\/([^)]+)\)/g,
      (match, alt: string, name: string) => {
        const dataUrl = artifact?.images?.[name];
        return dataUrl ? `![${alt}](${dataUrl})` : match;
      }
    );
    return DOMPurify.sanitize(marked.parse(source) as string, {
      USE_PROFILES: { html: true }
    });
  });
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
    await navigator.clipboard.writeText(content);
    copied = true;
    window.setTimeout(() => (copied = false), 1600);
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
  <title>dots.mocr · 文档解析工作台</title>
</svelte:head>

<div class="shell" class:detail-mode={view === 'detail'}>
  <aside class="sidebar">
    <button class="brand" onclick={() => updateRoute('new')} aria-label="返回新解析">
      <span class="brand-mark"><span></span><span></span><span></span></span>
      <span class="brand-copy"><strong>dots.mocr</strong><small>DOCUMENT LAB</small></span>
    </button>

    <nav aria-label="主导航">
      <button class:active={view === 'new'} onclick={() => updateRoute('new')}>
        <Plus size={19} strokeWidth={1.8} />
        <span>新解析</span>
      </button>
      <button class:active={view === 'tasks'} onclick={() => updateRoute('tasks')}>
        <Layers3 size={19} strokeWidth={1.8} />
        <span>任务管理</span>
        {#if activeTasks.length}<em>{activeTasks.length}</em>{/if}
      </button>
      <button class:active={view === 'logs'} onclick={() => { updateRoute('logs'); void refreshLogs(true); }}>
        <Terminal size={19} strokeWidth={1.8} />
        <span>服务日志</span>
      </button>
    </nav>

    <div class="sidebar-rule"></div>
    <div class="recent-label">最近完成</div>
    <div class="recent-list">
      {#each completedTasks.slice(0, 5) as task (task.task_id)}
        <button onclick={() => openTask(task.task_id)} title={task.original_names.join('、')}>
          <FileCheck2 size={15} />
          <span>{task.original_names[0] ?? task.file_names[0]}</span>
        </button>
      {:else}
        <p>暂无解析记录</p>
      {/each}
    </div>

    <div class="service-chip" class:offline={!health}>
      <span class="signal"></span>
      <div>
        <strong>{health ? '服务在线' : '连接中断'}</strong>
        <small>{health?.model_backend ?? '等待 API 响应'}</small>
      </div>
    </div>
  </aside>

  <main>
    {#if view === 'new'}
      <section class="new-view">
        <header class="topbar">
          <div class="crumb"><span>工作台</span><ChevronRight size={14} /><strong>新解析</strong></div>
          <div class="capacity">
            <span><i class="live-dot"></i>{health?.max_concurrent_requests ?? 2} 路并发</span>
            <span>{health?.processing_window_size ?? 64} 页窗口</span>
          </div>
        </header>

        <div class="new-content">
          <div class="eyebrow"><Sparkles size={15} /> DOCUMENT INTELLIGENCE</div>
          <h1>把文档，变成<br /><em>可用的结构。</em></h1>
          <p class="lead">上传 PDF 或图片，提交到 MinerU 兼容任务队列；解析完成后并排核对原文件、Markdown 与结构化 JSON。</p>

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
            <div class="drop-grid"></div>
            <button class="settings-button" onclick={() => (settingsOpen = !settingsOpen)}>
              <Settings2 size={16} />
              解析设置
            </button>

            {#if files.length === 0}
              <div class="drop-empty">
                <div class="file-stack" aria-hidden="true">
                  <span class="sheet image"><ImageIcon size={24} /></span>
                  <span class="sheet pdf">PDF</span>
                  <span class="sheet text"><FileText size={24} /></span>
                </div>
                <h2>拖入文档，开始解析</h2>
                <p>PDF · PNG · JPG · WEBP · TIFF · 最多 8 个文件</p>
                <button class="primary compact" onclick={() => fileInput?.click()}>
                  <Upload size={17} />选择文件
                </button>
              </div>
            {:else}
              <div class="file-selection">
                <div class="selection-head">
                  <div><strong>{files.length} 个文件已就绪</strong><span>将作为同一个解析任务提交</span></div>
                  <button onclick={() => fileInput?.click()}><Plus size={16} />继续添加</button>
                </div>
                <div class="file-list">
                  {#each files as file, index (`${file.name}-${file.size}`)}
                    <div class="file-row">
                      <span class="file-kind">{file.name.split('.').pop()?.slice(0, 4).toUpperCase()}</span>
                      <div><strong>{file.name}</strong><small>{formatSize(file.size)}</small></div>
                      <button onclick={() => removeFile(index)} aria-label={`移除 ${file.name}`}><X size={16} /></button>
                    </div>
                  {/each}
                </div>
                <button class="primary submit" disabled={submitting} onclick={createTask}>
                  {#if submitting}<LoaderCircle class="spin" size={18} />正在提交{:else}<Sparkles size={18} />提交解析{/if}
                </button>
              </div>
            {/if}

            <input bind:this={fileInput} class="visually-hidden" type="file" multiple accept={acceptedExtensions} onchange={onFileChange} />

            {#if settingsOpen}
              <div class="settings-panel">
                <div class="settings-title"><span>解析参数</span><button onclick={() => (settingsOpen = false)}><X size={16} /></button></div>
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

          {#if error}<div class="inline-error"><CircleAlert size={16} />{error}</div>{/if}

          <div class="service-strip">
            <div><Gauge size={17} /><span>队列</span><strong>{health?.queued_tasks ?? 0}</strong></div>
            <div><LoaderCircle size={17} /><span>解析中</span><strong>{health?.processing_tasks ?? 0}</strong></div>
            <div><Check size={17} /><span>本机已完成</span><strong>{completedTasks.length}</strong></div>
          </div>
        </div>
      </section>
    {:else if view === 'tasks'}
      <section class="tasks-view">
        <header class="topbar">
          <div class="crumb"><span>工作台</span><ChevronRight size={14} /><strong>任务管理</strong></div>
          <button class="refresh" class:spinning={refreshing} onclick={refresh}><RefreshCw size={16} />刷新</button>
        </header>
        <div class="tasks-content">
          <div class="section-heading">
            <div><span class="index">02</span><div><h1>任务管理</h1><p>当前浏览器提交的解析任务</p></div></div>
            <button class="primary compact" onclick={() => updateRoute('new')}><Plus size={17} />新解析</button>
          </div>

          <div class="task-summary">
            <article><FileClock size={19} /><div><span>等待 / 进行中</span><strong>{activeTasks.length}</strong></div></article>
            <article><FileCheck2 size={19} /><div><span>解析完成</span><strong>{completedTasks.length}</strong></div></article>
            <article><Inbox size={19} /><div><span>全部记录</span><strong>{tasks.length}</strong></div></article>
          </div>

          <div class="task-table">
            <div class="table-head"><span>文件</span><span>状态</span><span>提交时间</span><span>大小</span><span></span></div>
            {#each visibleTasks as task (task.task_id)}
              <button class="task-row" onclick={() => openTask(task.task_id)}>
                <span class="task-file">
                  <i><FileText size={18} /></i>
                  <span><strong>{task.original_names[0] ?? task.file_names[0]}</strong><small>{task.original_names.length > 1 ? `另有 ${task.original_names.length - 1} 个文件 · ` : ''}{task.task_id.slice(0, 8)}</small></span>
                </span>
                <span><i class={`status ${task.status}`}><b></b>{statusText(task.status)}</i>{#if task.queued_ahead}<small class="queued">前方 {task.queued_ahead} 项</small>{/if}</span>
                <span class="muted">{formatDate(task.created_at)}</span>
                <span class="muted">{formatSize(task.sizes.reduce((sum, size) => sum + size, 0))}</span>
                <span class="row-arrow"><ChevronRight size={17} /></span>
              </button>
            {:else}
              <div class="empty-tasks"><Inbox size={30} /><strong>还没有解析任务</strong><span>上传第一份文档后，任务会出现在这里。</span></div>
            {/each}
          </div>
        </div>
      </section>
    {:else if view === 'logs'}
      <section class="logs-view">
        <header class="topbar">
          <div class="crumb"><span>工作台</span><ChevronRight size={14} /><strong>服务日志</strong></div>
          <button class="refresh" class:spinning={logsLoading} onclick={() => refreshLogs(true)}><RefreshCw size={16} />刷新</button>
        </header>

        <div class="logs-content">
          <div class="logs-heading">
            <div>
              <span class="console-prompt">$</span>
              <div><h1>运行日志</h1><p>网关、任务队列与 vLLM 推理事件</p></div>
            </div>
            <div class="log-health" class:offline={!health}>
              <i></i><span>{health ? 'ALL SYSTEMS OPERATIONAL' : 'SERVICE UNREACHABLE'}</span>
            </div>
          </div>

          <div class="log-metrics">
            <article><span>GATEWAY</span><strong>{health ? 'ONLINE' : 'OFFLINE'}</strong><small>API 服务</small></article>
            <article><span>MODEL</span><strong>{health?.model_backend ?? '—'}</strong><small>推理后端</small></article>
            <article><span>QUEUE</span><strong>{health?.queued_tasks ?? 0}</strong><small>{health?.processing_tasks ?? 0} 个处理中</small></article>
            <article><span>BUFFER</span><strong>{serviceLogs.length}</strong><small>当前可见事件</small></article>
          </div>

          <div class="log-console">
            <div class="log-toolbar">
              <div class="level-filter" aria-label="日志级别">
                {#each ['all', 'info', 'warning', 'error'] as level}
                  <button class:active={logLevel === level} onclick={() => (logLevel = level as typeof logLevel)}>{level}</button>
                {/each}
              </div>
              <label class="log-search"><span>FILTER</span><input bind:value={logQuery} placeholder="任务 ID / 来源 / 消息" /></label>
              <button class="log-action" onclick={() => (logsPaused = !logsPaused)}>
                {#if logsPaused}<Play size={14} />继续{:else}<Pause size={14} />暂停{/if}
              </button>
              <button class="log-action" onclick={() => (serviceLogs = [])}>清空视图</button>
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
                <div class="empty-log"><Terminal size={28} /><strong>{logsLoading ? '正在连接日志流' : '没有匹配的日志'}</strong><span>新的服务事件会自动出现在这里</span></div>
              {/each}
            </div>

            <footer class="log-footer">
              <span><i class:paused={logsPaused}></i>{logsPaused ? 'STREAM PAUSED' : 'LIVE · 2.5S POLLING'}</span>
              <span>INSTANCE {logInstanceId.slice(0, 8) || '—'} · CURSOR {logCursor}</span>
            </footer>
          </div>
        </div>
      </section>
    {:else}
      <section class="detail-view">
        <header class="detail-header">
          <button class="back" onclick={() => updateRoute('tasks')}><ArrowLeft size={18} /></button>
          <div class="detail-title"><strong>{selectedTask?.original_names[0] ?? selectedTask?.file_names[0] ?? '解析任务'}</strong><span>{selectedTask?.task_id.slice(0, 8)}</span></div>
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
                <iframe src={originalUrl} title="原始 PDF"></iframe>
              {:else if originalUrl}
                <img src={originalUrl} alt={originalFile?.name ?? '原始文档'} />
              {:else}
                <div class="source-empty"><FileIcon size={36} /><strong>原文件不可用</strong><span>此任务不是在当前浏览器提交，或浏览器存储已清理。</span></div>
              {/if}
            </div>
          </section>

          <section class="result-pane">
            <div class="pane-bar result-bar">
              <div class="result-tabs">
                <button class:active={resultTab === 'markdown'} onclick={() => (resultTab = 'markdown')}>Markdown</button>
                <button class:active={resultTab === 'json'} onclick={() => (resultTab = 'json')}>JSON</button>
              </div>
              <button class="copy" disabled={!selectedArtifact} onclick={copyResult}>{#if copied}<Check size={16} />已复制{:else}<Clipboard size={16} />复制{/if}</button>
            </div>
            <div class="result-scroll">
              {#if resultLoading}
                <div class="result-state"><LoaderCircle class="spin" size={28} /><strong>正在读取结果</strong></div>
              {:else if selectedTask?.status === 'pending'}
                <div class="result-state queue-art"><Clock3 size={30} /><strong>任务正在排队</strong><span>前方还有 {selectedTask.queued_ahead ?? 0} 项任务</span></div>
              {:else if selectedTask?.status === 'processing'}
                <div class="result-state processing-art"><span class="scanner"></span><LoaderCircle class="spin" size={30} /><strong>正在解析文档</strong><span>页面处理完成后会自动显示结果</span></div>
              {:else if selectedTask?.status === 'failed' || selectedTask?.status === 'expired'}
                <div class="result-state failed-art"><CircleAlert size={30} /><strong>{statusText(selectedTask.status)}</strong><span>{selectedTask.error}</span></div>
              {:else if selectedArtifact && resultTab === 'markdown'}
                <article class="markdown-body">{@html markdownHtml}</article>
              {:else if selectedArtifact && resultTab === 'json'}
                <div class="json-view"><div class="json-label"><Code2 size={15} />{selectedArtifactName}.json</div><pre>{prettyJson}</pre></div>
              {:else}
                <div class="result-state"><PanelLeftClose size={30} /><strong>等待解析结果</strong></div>
              {/if}
            </div>
          </section>
        </div>
      </section>
    {/if}
  </main>
</div>
