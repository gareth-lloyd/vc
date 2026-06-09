// DRF field errors are usually `string[]`, but nested serializers yield nested
// objects and arrays-of-objects. Typed as `unknown` so consumers flatten
// honestly rather than trusting a `string[]` shape that can be a lie.
export type FieldErrors = Record<string, unknown>;

export interface ApiErrorBody {
  code?: string;
  detail?: string;
  field_errors?: FieldErrors;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly fieldErrors: FieldErrors;
  readonly body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null) {
    const detail = body?.detail ?? `Request failed with status ${status}`;
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? "unknown";
    this.detail = detail;
    this.fieldErrors = body?.field_errors ?? {};
    this.body = body;
  }

  isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }
}
