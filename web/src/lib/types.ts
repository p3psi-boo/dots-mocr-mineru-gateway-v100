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
  options?: SubmitOptions;
}

export interface FileResult {
  md_content?: string;
  middle_json?: string;
  model_output?: string;
  content_list?: string;
  images?: Record<string, string>;
}

export interface ContentListItem {
  type: string;
  page_idx?: number;
  bbox?: number[];
  text?: string;
  text_level?: number;
  table_body?: string;
  list_items?: string[];
  sub_type?: string;
  img_path?: string;
  [key: string]: unknown;
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
  endPage: number | null;
}

export interface Toast {
  id: number;
  kind: 'error' | 'success' | 'info';
  message: string;
}

export type ThemePreference = 'light' | 'dark' | 'system';

export interface ServiceLogEntry {
  sequence: number;
  timestamp: string;
  level: 'info' | 'warning' | 'error';
  source: string;
  message: string;
  context: Record<string, unknown>;
}

export interface ServiceLogResponse {
  instance_id: string;
  items: ServiceLogEntry[];
  latest_sequence: number;
  capacity: number;
}

export interface OpenApiSchema {
  type?: string;
  format?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  items?: OpenApiSchema;
  properties?: Record<string, OpenApiSchema>;
  required?: string[];
  oneOf?: OpenApiSchema[];
  anyOf?: OpenApiSchema[];
  allOf?: OpenApiSchema[];
  $ref?: string;
  [key: string]: unknown;
}

export interface OpenApiParameter {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema?: OpenApiSchema;
}

export interface OpenApiOperation {
  summary?: string;
  description?: string;
  operationId?: string;
  tags?: string[];
  parameters?: OpenApiParameter[];
  requestBody?: {
    required?: boolean;
    content?: Record<string, { schema?: OpenApiSchema }>;
  };
  responses?: Record<string, { description?: string; content?: Record<string, unknown> }>;
  security?: Record<string, string[]>[];
}

export interface OpenApiDocument {
  openapi: string;
  info: {
    title: string;
    version: string;
    summary?: string;
    description?: string;
  };
  tags?: { name: string; description?: string }[];
  paths: Record<string, Record<string, OpenApiOperation | unknown>>;
  components?: {
    schemas?: Record<string, OpenApiSchema>;
    securitySchemes?: Record<string, { type?: string; name?: string; in?: string; description?: string }>;
  };
}
