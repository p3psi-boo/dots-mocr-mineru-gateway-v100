import type {
  HealthStatus,
  ServiceLogResponse,
  SubmitOptions,
  TaskResult,
  TaskStatus
} from './types';

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
      message = payload.detail ?? payload.message ?? message;
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthStatus> {
  return json(await fetch('/health', { signal }));
}

export async function submitTask(
  files: File[],
  options: SubmitOptions
): Promise<TaskStatus> {
  const form = new FormData();
  for (const file of files) form.append('files', file);
  form.append('lang_list', options.lang);
  form.append('backend', 'pipeline');
  form.append('parse_method', options.parseMethod);
  form.append('formula_enable', String(options.formula));
  form.append('table_enable', String(options.table));
  form.append('image_analysis', String(options.images));
  form.append('return_md', 'true');
  form.append('return_middle_json', 'true');
  form.append('return_model_output', 'true');
  form.append('return_content_list', 'true');
  form.append('return_images', String(options.images));
  form.append('start_page_id', String(options.startPage));
  form.append('end_page_id', String(options.endPage));

  return json(
    await fetch('/tasks', {
      method: 'POST',
      body: form
    })
  );
}

export async function getTask(taskId: string): Promise<TaskStatus> {
  return json(await fetch(`/tasks/${encodeURIComponent(taskId)}`));
}

export async function getTaskResult(taskId: string): Promise<TaskResult> {
  return json(await fetch(`/tasks/${encodeURIComponent(taskId)}/result`));
}

export async function getServiceLogs(after = 0, limit = 200): Promise<ServiceLogResponse> {
  const query = new URLSearchParams({ after: String(after), limit: String(limit) });
  return json(await fetch(`/service/logs?${query}`));
}
