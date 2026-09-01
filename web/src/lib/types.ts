export type TaskState = 'pending' | 'processing' | 'completed' | 'failed' | 'expired';

export interface TaskStatus {
  task_id: string;
  status: TaskState;
  backend: string;
  file_names: string[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  status_url: string;
  result_url: string;
  queued_ahead?: number;
}

export interface TaskRecord extends TaskStatus {
  original_names: string[];
  sizes: number[];
}

export interface FileResult {
  md_content?: string;
  middle_json?: string;
  model_output?: string;
  content_list?: string;
  images?: Record<string, string>;
}

export interface TaskResult {
  backend: string;
  version: string;
  results: Record<string, FileResult>;
}

export interface HealthStatus {
  status: string;
  queued_tasks: number;
  processing_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  max_concurrent_requests: number;
  processing_window_size: number;
  task_retention_seconds: number;
  model_backend: string;
}

export interface SubmitOptions {
  lang: string;
  parseMethod: 'auto' | 'txt' | 'ocr';
  formula: boolean;
  table: boolean;
  images: boolean;
  startPage: number;
  endPage: number;
}
