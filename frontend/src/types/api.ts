export interface ApiErrorShape {
  code: string;
  message: string;
  detail?: string;
  trace_id?: string;
  extra?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  extra: Record<string, unknown>;

  constructor(status: number, payload: ApiErrorShape) {
    super(payload.message || `HTTP ${status}`);
    this.status = status;
    this.code = payload.code || 'UNKNOWN';
    this.detail = payload.detail || '';
    this.extra = payload.extra || {};
  }
}
