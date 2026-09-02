<script lang="ts">
  import { onMount, tick } from 'svelte';
  import {
    ArrowLeft,
    BookOpen,
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
    Keyboard,
    Layers3,
    ListTree,
    LoaderCircle,
    Minus,
    Moon,
    PanelLeftClose,
    Pause,
    Play,
    Plus,
    RefreshCw,
    RotateCcw,
    Search,
    Settings2,
    Square,
    Sun,
    Terminal,
    Trash2,
    Upload,
    X,
    ZoomIn,
    ZoomOut
  } from '@lucide/svelte';
  import DocumentOutline from '$lib/DocumentOutline.svelte';
  import ImageViewer from '$lib/ImageViewer.svelte';
  import InteractiveMarkdown from '$lib/InteractiveMarkdown.svelte';
  import JsonTree from '$lib/JsonTree.svelte';
  import OpenApiDocs from '$lib/OpenApiDocs.svelte';
  import { cancelTask, getHealth, getServiceLogs, getTask, getTaskResult, submitTask } from '$lib/api';
  import { isEditableTarget } from '$lib/bbox';
  import {
    acceptedExtensions,
    expandArtifact,
    formatDate,
    formatLogTime,
    formatSize,
    isCancelled,
    isOptionsChanged,
    maxFiles,
    mergeStatus,
    optionsSummary,
    statusText,
    supportedFilePattern,
    terminalStates
  } from '$lib/format';
  import { copyTextCompat, documentOutline, downloadBlob, interactiveBlocks, safeDownloadName } from '$lib/interactive-markdown';
  import {
    applyTheme,
    defaultOptions,
    deleteTaskAssets,
    loadFile,
    loadOptions,
    loadResult,
    loadTasks,
    loadTheme,
    saveFiles,
    saveOptions,
    saveResult,
    saveTasks,
    saveTheme
  } from '$lib/storage';
  import type {
    HealthStatus,
    ServiceLogEntry,
    SubmitOptions,
    TaskRecord,
    TaskResult,
    ThemePreference,
    Toast
  } from '$lib/types';

  type View = 'new' | 'tasks' | 'logs' | 'api' | 'detail';
  type ResultTab = 'markdown' | 'json';
  type ImageFit = 'contain' | 'width' | 'actual';

  const logLevels: { id: 'all' | ServiceLogEntry['level']; label: string }[] = [
    { id: 'all', label: '全部' },
    { id: 'info', label: '信息' },
    { id: 'warning', label: '警告' },
    { id: 'error', label: '错误' }
  ];

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
  let notices = $state<string[]>([]);
  let selectedTaskId = $state('');
  let selectedFileIndex = $state(0);
  let result = $state<TaskResult | null>(null);
  let resultLoading = $state(false);
  let resultError = $state('');
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
  let logsError = $state('');
  let logLevel = $state<'all' | ServiceLogEntry['level']>('all');
  let logQuery = $state('');
  let logViewport = $state<HTMLDivElement>();
  let logPinnedToBottom = $state(true);
  let unseenLogs = $state(0);
  let selectedBlockIndex = $state<number | null>(null);
  let outlineOpen = $state(true);
  let sourceZoom = $state(1);
  let imageFit = $state<ImageFit>('contain');
  let pdfPage = $state(1);
  let pdfPages = $state(0);
  let paramsOpen = $state(false);
  let shortcutsOpen = $state(false);
  let theme = $state<ThemePreference>('system');
  let toasts = $state<Toast[]>([]);
  let optionsReady = $state(false);
  let toastSeq = 0;

  const activeTasks = $derived(tasks.filter((task) => !terminalStates.includes(task.status)));
  const completedTasks = $derived(tasks.filter((task) => task.status === 'completed'));
  const failedTasks = $derived(tasks.filter((task) => task.status === 'failed' || task.status === 'expired'));
  const selectedTask = $derived(tasks.find((task) => task.task_id === selectedTaskId) ?? null);
  const artifactNames = $derived(result ? Object.keys(result.results) : selectedTask?.file_names ?? []);
  const selectedArtifactName = $derived(artifactNames[selectedFileIndex] ?? artifactNames[0] ?? '');
  const selectedArtifact = $derived(
    result && selectedArtifactName ? result.results[selectedArtifactName] : undefined
  );
  const resultBlocks = $derived(selectedArtifact ? interactiveBlocks(selectedArtifact) : []);
  const outlineEntries = $derived(documentOutline(resultBlocks));
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
  const prettyJson = $derived(JSON.stringify(expandArtifact(selectedArtifact), null, 2));
  const optionsDirty = $derived(isOptionsChanged(options));
  const pageWindow = $derived(health?.processing_window_size ?? 64);
  const isPdfOriginal = $derived(
    Boolean(originalFile && (originalFile.type === 'application/pdf' || /\.pdf$/i.test(originalFile.name)))
  );
  const resolvedDark = $derived(theme === 'dark' || (theme === 'system' && typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches));

  function persist(next: TaskRecord[]): void {
    tasks = next;
    try {
      saveTasks(next);
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '无法保存任务列表', 'error');
    }
  }

  function pushToast(message: string, kind: Toast['kind'] = 'error'): void {
    const id = ++toastSeq;
    toasts = [...toasts, { id, kind, message }];
    window.setTimeout(() => dismissToast(id), kind === 'error' ? 8000 : 4000);
  }

  function dismissToast(id: number): void {
    toasts = toasts.filter((toast) => toast.id !== id);
  }

  function reportError(message: string): void {
    error = message;
    pushToast(message, 'error');
  }

  function updateRoute(nextView: View, taskId = '', replace = false): void {
    view = nextView;
    selectedTaskId = taskId;
    const url = new URL(window.location.href);
    url.search = '';
    if (nextView === 'tasks') url.searchParams.set('view', 'tasks');
    if (nextView === 'logs') url.searchParams.set('view', 'logs');
    if (nextView === 'api') url.searchParams.set('view', 'api');
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
      view = requestedView === 'tasks' || requestedView === 'logs' || requestedView === 'api'
        ? requestedView
        : 'new';
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
      reportError(caught instanceof Error ? caught.message : '任务不存在');
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

  function isLogAtBottom(element: HTMLElement): boolean {
    return element.scrollHeight - element.scrollTop - element.clientHeight < 48;
  }

  function onLogScroll(): void {
    if (!logViewport) return;
    if (isLogAtBottom(logViewport)) {
      logPinnedToBottom = true;
      unseenLogs = 0;
    } else {
      logPinnedToBottom = false;
    }
  }

  function jumpToLatestLogs(): void {
    if (!logViewport) return;
    logViewport.scrollTop = logViewport.scrollHeight;
    logPinnedToBottom = true;
    unseenLogs = 0;
  }

  async function refreshLogs(reset = false): Promise<void> {
    if (logsLoading || (logsPaused && !reset)) return;
    logsLoading = true;
    try {
      const response = await getServiceLogs(reset ? 0 : logCursor, reset ? 300 : 200);
      const restarted = logInstanceId !== '' && logInstanceId !== response.instance_id;
      const known = new Set(serviceLogs.map((entry) => entry.sequence));
      let added = 0;
      if (reset || restarted) {
        serviceLogs = response.items;
        unseenLogs = 0;
        logPinnedToBottom = true;
      } else if (response.items.length) {
        const incoming = response.items.filter((entry) => !known.has(entry.sequence));
        added = incoming.length;
        serviceLogs = [...serviceLogs, ...incoming].slice(-response.capacity);
      }
      logInstanceId = response.instance_id;
      logCursor = response.items.at(-1)?.sequence ?? response.latest_sequence;
      logsError = '';
      await tick();
      if (logViewport && logPinnedToBottom) logViewport.scrollTop = logViewport.scrollHeight;
      else if (added) unseenLogs += added;
    } catch (caught) {
      logsError = caught instanceof Error ? caught.message : '日志读取失败';
      reportError(logsError);
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

  async function addFiles(nextFiles: File[]): Promise<void> {
    error = '';
    const messages: string[] = [];
    const supported: File[] = [];
    for (const file of nextFiles) {
      if (supportedFilePattern.test(file.name)) supported.push(file);
      else messages.push(`${file.name}：不支持的格式`);
    }
    const merged = [...files, ...supported];
    const unique: File[] = [];
    const duplicates: string[] = [];
    for (const file of merged) {
      if (unique.some((other) => other.name === file.name && other.size === file.size)) {
        duplicates.push(file.name);
      } else {
        unique.push(file);
      }
    }
    if (duplicates.length) messages.push(`已跳过重复文件：${[...new Set(duplicates)].join('、')}`);
    if (unique.length > maxFiles) {
      const dropped = unique.slice(maxFiles);
      messages.push(`最多 ${maxFiles} 个文件，已忽略：${dropped.map((file) => file.name).join('、')}`);
      files = unique.slice(0, maxFiles);
    } else {
      files = unique;
    }
    const windowSize = pageWindow;
    if (files.some((file) => file.type === 'application/pdf' || /\.pdf$/i.test(file.name))) {
      const { countPdfPages } = await import('$lib/pdf');
      for (const file of files) {
        const pages = await countPdfPages(file);
        if (pages && pages > windowSize && options.endPage === null) {
          messages.push(`${file.name} 共 ${pages} 页，超出单次 ${windowSize} 页上限，请在设置中指定页范围`);
        }
      }
    }
    notices = messages;
  }

  function onFileChange(event: Event): void {
    const target = event.currentTarget as HTMLInputElement;
    void addFiles(Array.from(target.files ?? []));
    target.value = '';
  }

  function onDrop(event: DragEvent): void {
    event.preventDefault();
    dragging = false;
    void addFiles(Array.from(event.dataTransfer?.files ?? []));
  }

  function removeFile(index: number): void {
    files = files.filter((_, fileIndex) => fileIndex !== index);
  }

  function setAllPages(all: boolean): void {
    options = all
      ? { ...options, startPage: 0, endPage: null }
      : { ...options, endPage: pageWindow - 1 };
  }

  async function createTask(): Promise<void> {
    if (files.length === 0 || submitting) return;
    submitting = true;
    error = '';
    try {
      const submittedFiles = [...files];
      const snapshot: SubmitOptions = { ...options };
      const status = await submitTask(submittedFiles, snapshot);
      const record: TaskRecord = {
        ...status,
        original_names: submittedFiles.map((file) => file.name),
        sizes: submittedFiles.map((file) => file.size),
        options: snapshot
      };
      await saveFiles(status.task_id, submittedFiles);
      persist([record, ...tasks.filter((task) => task.task_id !== record.task_id)]);
      files = [];
      notices = [];
      await openTask(record.task_id);
    } catch (caught) {
      reportError(caught instanceof Error ? caught.message : '提交失败');
    } finally {
      submitting = false;
    }
  }

  async function openTask(taskId: string): Promise<void> {
    updateRoute('detail', taskId);
    selectedFileIndex = 0;
    selectedBlockIndex = null;
    resultTab = 'markdown';
    resultError = '';
    paramsOpen = false;
    sourceZoom = 1;
    imageFit = 'contain';
    error = '';
    await loadSelectedTask();
  }

  async function loadSelectedTask(): Promise<void> {
    if (!selectedTaskId) return;
    resultLoading = true;
    resultError = '';
    result = (await loadResult(selectedTaskId)) ?? null;
    if (!result && selectedTask?.status === 'completed') {
      try {
        result = await getTaskResult(selectedTaskId);
        await saveResult(selectedTaskId, result);
      } catch (caught) {
        resultError = caught instanceof Error ? caught.message : '结果读取失败';
        reportError(resultError);
      }
    }
    await loadOriginal(selectedTaskId, selectedFileIndex);
    resultLoading = false;
  }

  async function selectFile(index: number): Promise<void> {
    selectedFileIndex = index;
    selectedBlockIndex = null;
    sourceZoom = 1;
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

  function exportMarkdown(): void {
    if (!selectedArtifact?.md_content) return;
    downloadBlob(
      selectedArtifact.md_content,
      'text/markdown;charset=utf-8',
      safeDownloadName(selectedArtifactName, 'md')
    );
  }

  function contextEntries(context: Record<string, unknown>): [string, string][] {
    return Object.entries(context)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => [key, typeof value === 'string' ? value : JSON.stringify(value)]);
  }

  function selectBlock(index: number): void {
    selectedBlockIndex = index;
    if (resultTab !== 'markdown') resultTab = 'markdown';
  }

  function moveBlock(delta: number): void {
    const count = resultBlocks.length;
    if (!count) return;
    const current = selectedBlockIndex ?? (delta > 0 ? -1 : count);
    const next = current + delta;
    if (next < 0 || next >= count) return;
    selectedBlockIndex = next;
    if (resultTab !== 'markdown') resultTab = 'markdown';
  }

  function moveFile(delta: number): void {
    if (artifactNames.length < 2) return;
    const next = selectedFileIndex + delta;
    if (next < 0 || next >= artifactNames.length) return;
    void selectFile(next);
  }

  async function cancelExisting(task: TaskRecord): Promise<void> {
    try {
      const status = await cancelTask(task.task_id);
      persist(tasks.map((item) => (item.task_id === task.task_id ? mergeStatus(item, status) : item)));
      pushToast('任务已取消', 'info');
    } catch (caught) {
      reportError(caught instanceof Error ? caught.message : '取消失败');
    }
  }

  async function retryTask(task: TaskRecord): Promise<void> {
    const recovered: File[] = [];
    for (let index = 0; index < task.original_names.length; index += 1) {
      const file = await loadFile(task.task_id, index);
      if (!file) {
        reportError('原文件不可用，无法重试。请重新上传。');
        return;
      }
      recovered.push(file);
    }
    submitting = true;
    try {
      const snapshot = task.options ?? options;
      const status = await submitTask(recovered, snapshot);
      const record: TaskRecord = {
        ...status,
        original_names: recovered.map((file) => file.name),
        sizes: recovered.map((file) => file.size),
        options: { ...snapshot }
      };
      await saveFiles(status.task_id, recovered);
      persist([record, ...tasks.filter((item) => item.task_id !== record.task_id)]);
      pushToast('已重新提交', 'success');
      await openTask(record.task_id);
    } catch (caught) {
      reportError(caught instanceof Error ? caught.message : '重试失败');
    } finally {
      submitting = false;
    }
  }

  async function removeTask(task: TaskRecord): Promise<void> {
    if (!window.confirm(`确定删除「${task.original_names[0] ?? task.file_names[0]}」？本地结果和原文件会一并移除。`)) {
      return;
    }
    if (!terminalStates.includes(task.status)) {
      try {
        await cancelTask(task.task_id);
      } catch {
        // Local deletion should still proceed if the server task is already gone.
      }
    }
    await deleteTaskAssets(task.task_id, Math.max(task.original_names.length, task.file_names.length, 1));
    persist(tasks.filter((item) => item.task_id !== task.task_id));
    if (selectedTaskId === task.task_id) updateRoute('tasks');
    pushToast('任务已删除', 'info');
  }

  async function clearCompleted(): Promise<void> {
    const removable = tasks.filter((task) => task.status === 'completed' || task.status === 'expired');
    if (!removable.length) return;
    if (!window.confirm(`清理 ${removable.length} 条已完成/已过期任务？`)) return;
    await Promise.all(
      removable.map((task) =>
        deleteTaskAssets(task.task_id, Math.max(task.original_names.length, task.file_names.length, 1))
      )
    );
    persist(tasks.filter((task) => task.status !== 'completed' && task.status !== 'expired'));
    if (selectedTask && (selectedTask.status === 'completed' || selectedTask.status === 'expired')) {
      updateRoute('tasks');
    }
    pushToast('已清理完成的任务', 'info');
  }

  function cycleTheme(): void {
    theme = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light';
    saveTheme(theme);
    applyTheme(theme);
  }

  function themeLabel(value: ThemePreference): string {
    return { light: '浅色', dark: '深色', system: '跟随系统' }[value];
  }

  function onGlobalKey(event: KeyboardEvent): void {
    if (event.key === '?' && !event.metaKey && !event.ctrlKey && !event.altKey && !isEditableTarget(event.target)) {
      event.preventDefault();
      shortcutsOpen = !shortcutsOpen;
      return;
    }
    if (event.key === 'Escape') {
      if (shortcutsOpen) {
        shortcutsOpen = false;
        return;
      }
      if (settingsOpen) {
        settingsOpen = false;
        return;
      }
      if (selectedBlockIndex !== null) {
        selectedBlockIndex = null;
        return;
      }
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (view !== 'logs' && view !== 'api') {
        updateRoute('logs');
        void refreshLogs(true).then(() => document.getElementById('log-search-input')?.focus());
      } else {
        document.getElementById(view === 'api' ? 'api-search-input' : 'log-search-input')?.focus();
      }
      return;
    }
    if (isEditableTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
    if (view !== 'detail') return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      moveFile(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      moveFile(1);
    } else if (event.key === 'j' || event.key === 'J') {
      event.preventDefault();
      moveBlock(1);
    } else if (event.key === 'k' || event.key === 'K') {
      event.preventDefault();
      moveBlock(-1);
    }
  }

  $effect(() => {
    if (!optionsReady) return;
    saveOptions(options);
  });

  onMount(() => {
    tasks = loadTasks();
    options = loadOptions();
    theme = loadTheme();
    applyTheme(theme);
    optionsReady = true;
    void readRoute();
    void refresh();
    const poller = window.setInterval(() => void refresh(), 2500);
    const onPopState = () => void readRoute();
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onScheme = () => applyTheme(theme);
    window.addEventListener('popstate', onPopState);
    window.addEventListener('keydown', onGlobalKey);
    media.addEventListener('change', onScheme);
    return () => {
      window.clearInterval(poller);
      window.removeEventListener('popstate', onPopState);
      window.removeEventListener('keydown', onGlobalKey);
      media.removeEventListener('change', onScheme);
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
      <button class:active={view === 'api'} onclick={() => updateRoute('api')}>
        <BookOpen size={18} strokeWidth={1.8} />
        <span>API 文档</span>
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
      {#if completedTasks.length > 5}
        <button class="recent-more" onclick={() => updateRoute('tasks')}>查看全部 {completedTasks.length} 条</button>
      {/if}
    </div>

    <button class="theme-toggle" onclick={cycleTheme} aria-label={`外观：${themeLabel(theme)}`}>
      {#if resolvedDark}<Moon size={15} />{:else}<Sun size={15} />{/if}
      <span>{themeLabel(theme)}</span>
    </button>

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
            <button
              class="settings-button"
              class:dirty={optionsDirty}
              onclick={() => (settingsOpen = !settingsOpen)}
              aria-label={optionsDirty ? `解析设置，当前：${optionsSummary(options)}` : '解析设置'}
            >
              <Settings2 size={16} />
              {#if optionsDirty}<i class="settings-dot"></i>{/if}
            </button>
            {#if optionsDirty && !settingsOpen}
              <p class="settings-hint">{optionsSummary(options)}</p>
            {/if}

            {#if files.length === 0}
              <button class="drop-empty" onclick={() => fileInput?.click()}>
                <span class="drop-icon"><Upload size={22} strokeWidth={1.8} /></span>
                <strong>拖入文件，或点击选择</strong>
                <small>PDF · PNG · JPG · WEBP · TIFF，最多 {maxFiles} 个</small>
                <p class="drop-hint">上传后可获得可编辑的 Markdown、结构化 JSON 和表格 CSV。默认解析全部页，点右上角齿轮可限制页范围、语言和公式/表格识别。</p>
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
                <label class="toggle">
                  <span>全部页</span>
                  <input type="checkbox" checked={options.endPage === null} onchange={(event) => setAllPages((event.currentTarget as HTMLInputElement).checked)} />
                  <i></i>
                </label>
                {#if options.endPage !== null}
                  <div class="page-range">
                    <label>起始页
                      <input
                        type="number"
                        min="1"
                        value={options.startPage + 1}
                        oninput={(event) => {
                          options.startPage = Math.max(0, Number((event.currentTarget as HTMLInputElement).value) - 1);
                        }}
                      />
                    </label>
                    <label>结束页
                      <input
                        type="number"
                        min={options.startPage + 1}
                        value={options.endPage + 1}
                        oninput={(event) => {
                          options.endPage = Math.max(options.startPage, Number((event.currentTarget as HTMLInputElement).value) - 1);
                        }}
                      />
                    </label>
                  </div>
                {/if}
                <p class="settings-note">页码从 1 开始。服务单次最多解析 {pageWindow} 页，超出将失败。</p>
                <label class="toggle"><span>公式识别</span><input type="checkbox" bind:checked={options.formula} /><i></i></label>
                <label class="toggle"><span>表格识别</span><input type="checkbox" bind:checked={options.table} /><i></i></label>
                <label class="toggle"><span>图片区域</span><input type="checkbox" bind:checked={options.images} /><i></i></label>
              </div>
            {/if}
          </div>

          {#if notices.length}
            <div class="inline-error" role="alert">
              <CircleAlert size={15} />
              <ul>{#each notices as notice}<li>{notice}</li>{/each}</ul>
            </div>
          {/if}
          {#if error}<div class="inline-error" role="alert"><CircleAlert size={15} />{error}</div>{/if}
        </div>
      </section>
    {:else if view === 'tasks'}
      <section class="tasks-view">
        <header class="page-head">
          <div>
            <h1>任务</h1>
            <p>{activeTasks.length} 进行中 · {completedTasks.length} 已完成 · {failedTasks.length} 失败/过期</p>
          </div>
          <div class="head-actions">
            <button class="ghost refresh" class:spinning={refreshing} onclick={refresh} aria-label="刷新"><RefreshCw size={15} /></button>
            <button class="ghost" disabled={!completedTasks.length && !tasks.some((task) => task.status === 'expired')} onclick={() => void clearCompleted()}>清理已完成</button>
            <button class="primary compact" onclick={() => updateRoute('new')}><Plus size={16} />新解析</button>
          </div>
        </header>

        <div class="task-table">
          {#each visibleTasks as task (task.task_id)}
            <div class="task-row">
              <button class="task-main" onclick={() => openTask(task.task_id)}>
                <span class="task-file">
                  <i><FileText size={17} /></i>
                  <span>
                    <strong>{task.original_names[0] ?? task.file_names[0]}</strong>
                    <small>
                      {task.original_names.length > 1 ? `${task.original_names.length} 个文件 · ` : ''}{formatDate(task.created_at)} · {formatSize(task.sizes.reduce((sum, size) => sum + size, 0))}
                      {#if task.options}<span> · {optionsSummary(task.options)}</span>{/if}
                    </small>
                    {#if (task.status === 'failed' || task.status === 'expired') && task.error}
                      <small class="task-error-inline">{task.error}</small>
                    {/if}
                  </span>
                </span>
                <span class="task-status">
                  <i class={`status ${task.status}${isCancelled(task) ? ' cancelled' : ''}`}><b></b>{statusText(task.status, task.error)}</i>
                  {#if task.queued_ahead}<small class="queued">前方 {task.queued_ahead} 项</small>{/if}
                </span>
                <span class="row-arrow"><ChevronRight size={16} /></span>
              </button>
              <div class="task-actions">
                {#if task.status === 'pending' || task.status === 'processing'}
                  <button type="button" title="取消" aria-label="取消任务" onclick={() => void cancelExisting(task)}><Square size={14} /></button>
                {/if}
                {#if task.status === 'failed' || task.status === 'expired'}
                  <button type="button" title="重试" aria-label="重试任务" onclick={() => void retryTask(task)}><RotateCcw size={14} /></button>
                {/if}
                <button type="button" title="删除" aria-label="删除任务" onclick={() => void removeTask(task)}><Trash2 size={14} /></button>
              </div>
            </div>
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

        {#if logsError}
          <div class="inline-error log-banner" role="alert"><CircleAlert size={15} />{logsError}</div>
        {/if}

        <div class="log-console">
          <div class="log-toolbar">
            <div class="level-filter" role="group" aria-label="日志级别">
              {#each logLevels as level}
                <button
                  class:active={logLevel === level.id}
                  aria-pressed={logLevel === level.id}
                  onclick={() => (logLevel = level.id)}
                >{level.label}</button>
              {/each}
            </div>
            <label class="log-search">
              <Search size={14} strokeWidth={2} />
              <input id="log-search-input" bind:value={logQuery} placeholder="筛选任务 ID、来源或消息" aria-label="筛选日志" />
            </label>
            <button class="log-action" onclick={() => (logsPaused = !logsPaused)}>
              {#if logsPaused}<Play size={14} strokeWidth={2} />继续{:else}<Pause size={14} strokeWidth={2} />暂停{/if}
            </button>
            <button class="log-action" onclick={() => (serviceLogs = [])}><Trash2 size={14} strokeWidth={2} />清空</button>
          </div>

          <div class="log-stream-wrap">
            <div class="log-stream" bind:this={logViewport} onscroll={onLogScroll}>
              {#each visibleLogs as entry (entry.sequence)}
                <article class={`log-entry ${entry.level}`}>
                  <time>{formatLogTime(entry.timestamp)}</time>
                  <span class="log-level">{entry.level === 'warning' ? 'WARN' : entry.level.toUpperCase()}</span>
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
                <div class="empty-log"><Terminal size={26} /><strong>{logsLoading ? '正在连接日志流' : logsError ? logsError : '没有匹配的日志'}</strong></div>
              {/each}
            </div>
            {#if unseenLogs > 0 && !logPinnedToBottom}
              <button class="log-jump" onclick={jumpToLatestLogs}>{unseenLogs} 条新日志，点击跳到最新</button>
            {/if}
          </div>
        </div>
      </section>
    {:else if view === 'api'}
      <OpenApiDocs />
    {:else}
      <section class="detail-view">
        <header class="detail-header">
          <button class="back" onclick={() => updateRoute('tasks')} aria-label="返回任务列表"><ArrowLeft size={17} /></button>
          <div class="detail-title">
            <strong>{selectedTask?.original_names[0] ?? selectedTask?.file_names[0] ?? '解析任务'}</strong>
            {#if selectedTask?.options}
              <button class="params-toggle" onclick={() => (paramsOpen = !paramsOpen)} aria-expanded={paramsOpen}>
                {paramsOpen ? '收起参数' : '查看参数'}
              </button>
            {/if}
          </div>
          {#if selectedTask}<i class={`status ${selectedTask.status}${isCancelled(selectedTask) ? ' cancelled' : ''}`}><b></b>{statusText(selectedTask.status, selectedTask.error)}</i>{/if}
          <div class="detail-spacer"></div>
          {#if selectedTask && (selectedTask.status === 'pending' || selectedTask.status === 'processing')}
            <button class="ghost compact" onclick={() => void cancelExisting(selectedTask)}>取消</button>
          {/if}
          {#if selectedTask && (selectedTask.status === 'failed' || selectedTask.status === 'expired')}
            <button class="ghost compact" onclick={() => void retryTask(selectedTask)}><RotateCcw size={14} />重试</button>
          {/if}
          {#if selectedTask}
            <button class="ghost compact" onclick={() => void removeTask(selectedTask)}><Trash2 size={14} />删除</button>
          {/if}
          {#if artifactNames.length > 1}
            <select class="file-switcher" value={selectedFileIndex} onchange={(event) => selectFile(Number((event.currentTarget as HTMLSelectElement).value))}>
              {#each artifactNames as name, index}<option value={index}>{name}</option>{/each}
            </select>
          {/if}
        </header>
        {#if paramsOpen && selectedTask?.options}
          <div class="params-bar">{optionsSummary(selectedTask.options)}</div>
        {/if}

        <div class="viewer">
          <section class="source-pane">
            <div class="pane-bar">
              <span>原文件</span>
              <div class="source-tools">
                {#if isPdfOriginal && pdfPages}
                  <small>第 {pdfPage} / {pdfPages} 页</small>
                {/if}
                {#if originalUrl && !isPdfOriginal}
                  <button class:active={imageFit === 'contain'} onclick={() => (imageFit = 'contain')}>适应</button>
                  <button class:active={imageFit === 'width'} onclick={() => (imageFit = 'width')}>宽度</button>
                  <button class:active={imageFit === 'actual'} onclick={() => { imageFit = 'actual'; sourceZoom = 1; }}>100%</button>
                {/if}
                {#if originalUrl}
                  <button aria-label="缩小" onclick={() => (sourceZoom = Math.max(0.25, sourceZoom / 1.25))}><ZoomOut size={14} /></button>
                  <button aria-label="放大" onclick={() => (sourceZoom = Math.min(4, sourceZoom * 1.25))}><ZoomIn size={14} /></button>
                  <button aria-label="重置缩放" onclick={() => (sourceZoom = 1)}><Minus size={14} /></button>
                {/if}
                <small>{originalFile ? formatSize(originalFile.size) : '仅保存在当前浏览器'}</small>
              </div>
            </div>
            <div class="source-stage">
              {#if originalUrl && isPdfOriginal}
                {#await import('$lib/PdfViewer.svelte')}
                  <div class="source-empty"><LoaderCircle class="spin" size={26} /><strong>正在加载 PDF 预览</strong></div>
                {:then module}
                  {@const PdfViewer = module.default}
                  <PdfViewer
                    url={originalUrl}
                    blocks={resultBlocks}
                    selectedIndex={selectedBlockIndex}
                    zoom={sourceZoom}
                    onSelectBlock={selectBlock}
                    onPageChange={(page, total) => { pdfPage = page; pdfPages = total; }}
                  />
                {:catch}
                  <div class="source-empty"><CircleAlert size={26} /><strong>PDF 预览加载失败</strong></div>
                {/await}
              {:else if originalUrl}
                <ImageViewer
                  url={originalUrl}
                  alt={originalFile?.name ?? '原始文档'}
                  blocks={resultBlocks}
                  selectedIndex={selectedBlockIndex}
                  fit={imageFit}
                  zoom={sourceZoom}
                  onSelectBlock={selectBlock}
                />
              {:else}
                <div class="source-empty"><FileIcon size={32} /><strong>原文件不可用</strong><span>此任务不是在当前浏览器提交，或浏览器存储已清理。</span></div>
              {/if}
            </div>
          </section>

          <section class="result-pane">
            <div class="pane-bar result-bar">
              <div class="result-tabs" role="tablist" aria-label="结果格式">
                <button
                  id="tab-markdown"
                  role="tab"
                  aria-selected={resultTab === 'markdown'}
                  aria-controls="panel-result"
                  class:active={resultTab === 'markdown'}
                  onclick={() => (resultTab = 'markdown')}
                >Markdown</button>
                <button
                  id="tab-json"
                  role="tab"
                  aria-selected={resultTab === 'json'}
                  aria-controls="panel-result"
                  class:active={resultTab === 'json'}
                  onclick={() => (resultTab = 'json')}
                >JSON</button>
              </div>
              <div class="result-actions">
                {#if resultTab === 'markdown' && outlineEntries.length}
                  <button
                    class="copy"
                    aria-pressed={outlineOpen}
                    onclick={() => (outlineOpen = !outlineOpen)}
                    title="目录"
                  >
                    <ListTree size={15} />目录
                  </button>
                {/if}
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
            <div
              class="result-body"
              class:no-outline={!outlineOpen || resultTab !== 'markdown' || !outlineEntries.length}
              id="panel-result"
              role="tabpanel"
              aria-labelledby={resultTab === 'markdown' ? 'tab-markdown' : 'tab-json'}
            >
              {#if outlineOpen && resultTab === 'markdown' && outlineEntries.length}
                <DocumentOutline entries={outlineEntries} selectedIndex={selectedBlockIndex} onJump={selectBlock} />
              {/if}
              <div class="result-scroll">
                {#if resultLoading}
                  <div class="result-state"><LoaderCircle class="spin" size={26} /><strong>正在读取结果</strong></div>
                {:else if resultError}
                  <div class="result-state failed-art"><CircleAlert size={28} /><strong>结果读取失败</strong><span>{resultError}</span></div>
                {:else if selectedTask?.status === 'pending'}
                  <div class="result-state"><Clock3 size={28} /><strong>排队中</strong><span>前方还有 {selectedTask.queued_ahead ?? 0} 项任务</span></div>
                {:else if selectedTask?.status === 'processing'}
                  <div class="result-state processing-art"><span class="scanner"></span><LoaderCircle class="spin" size={28} /><strong>正在解析</strong><span>完成后会自动显示结果</span></div>
                {:else if selectedTask?.status === 'failed' || selectedTask?.status === 'expired'}
                  <div class="result-state failed-art"><CircleAlert size={28} /><strong>{statusText(selectedTask.status, selectedTask.error)}</strong><span>{selectedTask.error}</span></div>
                {:else if selectedArtifact && resultTab === 'markdown'}
                  {#key selectedArtifactName}
                    <InteractiveMarkdown artifact={selectedArtifact} filename={selectedArtifactName} bind:selectedIndex={selectedBlockIndex} />
                  {/key}
                {:else if selectedArtifact && resultTab === 'json'}
                  <JsonTree value={expandArtifact(selectedArtifact)} filename={`${selectedArtifactName}.json`} />
                {:else}
                  <div class="result-state"><PanelLeftClose size={28} /><strong>等待解析结果</strong></div>
                {/if}
              </div>
            </div>
          </section>
        </div>
      </section>
    {/if}
  </main>
</div>

<div class="toast-host" aria-live="polite" aria-relevant="additions">
  {#each toasts as toast (toast.id)}
    <div class={`app-toast ${toast.kind}`} role="status">
      {#if toast.kind === 'error'}<CircleAlert size={15} />{:else}<Check size={15} />{/if}
      <span>{toast.message}</span>
      <button type="button" aria-label="关闭提示" onclick={() => dismissToast(toast.id)}><X size={14} /></button>
    </div>
  {/each}
</div>

{#if shortcutsOpen}
  <div class="shortcut-overlay">
    <button class="shortcut-backdrop" type="button" aria-label="关闭快捷键" onclick={() => (shortcutsOpen = false)}></button>
    <div class="shortcut-panel" role="dialog" aria-modal="true" aria-labelledby="shortcut-title" tabindex="-1">
      <div class="settings-title">
        <span id="shortcut-title"><Keyboard size={16} /> 快捷键</span>
        <button onclick={() => (shortcutsOpen = false)} aria-label="关闭"><X size={15} /></button>
      </div>
      <dl class="shortcut-list">
        <div><dt>← / →</dt><dd>切换文件</dd></div>
        <div><dt>J / K</dt><dd>下一块 / 上一块</dd></div>
        <div><dt>Esc</dt><dd>取消选中</dd></div>
        <div><dt>⌘K / Ctrl+K</dt><dd>搜索日志或 API</dd></div>
        <div><dt>?</dt><dd>显示快捷键</dd></div>
      </dl>
    </div>
  </div>
{/if}
