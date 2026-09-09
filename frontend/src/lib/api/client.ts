import { ApiError, type ApiErrorBody } from "./errors";
import { authChannel } from "./authChannel";
import { buildQuery, joinUrl, type QueryParams } from "./url";

const API_PREFIX = "/api/v1";
const UNSAFE_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

type SendMethod = "POST" | "PATCH" | "PUT" | "DELETE";

interface RequestOptions {
  query?: QueryParams;
  signal?: AbortSignal;
}

function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "";
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function buildHeaders(method: string, hasJsonBody: boolean): Headers {
  // A FormData body must NOT get an explicit Content-Type — the browser sets
  // multipart/form-data with its boundary.
  const headers = new Headers({ Accept: "application/json" });
  if (hasJsonBody) headers.set("Content-Type", "application/json");
  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCookie("csrftoken");
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  return headers;
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody | null> {
  try {
    const text = await response.text();
    if (!text) return null;
    return JSON.parse(text) as ApiErrorBody;
  } catch {
    return null;
  }
}

/**
 * Prime the `csrftoken` cookie (`GET /auth/csrf`). Deliberately a raw fetch:
 * a prime is best-effort, so a failure must not throw shaped errors or trip
 * the 401 auth channel the way `handleResponse` does.
 */
export async function primeCsrfCookie(): Promise<boolean> {
  try {
    const response = await fetch(joinUrl(apiBase(), `${API_PREFIX}/auth/csrf`), {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

function isCsrfReject(response: Response): boolean {
  // CsrfViewMiddleware rejects before the view (and before DRF's JSON
  // exception handler), so a CSRF failure is the only 403 this API returns
  // without a JSON body.
  return response.status === 403 && !(response.headers.get("content-type") ?? "").includes("json");
}

/**
 * Turn a non-2xx into the shaped `ApiError` every call site handles, and fire
 * the auth-channel side effects. Split out of `handleResponse` so the blob
 * reader below shares one definition of "this request failed" — a download
 * that 401s must log the tab out exactly like a JSON call does.
 */
async function throwIfNotOk(response: Response): Promise<void> {
  if (response.status === 401) {
    authChannel.emitUnauthorized();
    throw new ApiError(401, await parseErrorBody(response));
  }
  if (!response.ok) {
    const body = await parseErrorBody(response);
    // A staff user who hasn't enrolled in 2FA — route them to enrolment
    // (keeps the session, unlike the 401 logout path). CSRF-reject 403s have
    // no JSON body, so `code` is absent and this never mis-fires on them.
    if (response.status === 403 && body?.code === "tfa_enrollment_required") {
      authChannel.emitEnrollmentRequired();
    }
    throw new ApiError(response.status, body);
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  await throwIfNotOk(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function request<T>(
  method: string,
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const url = joinUrl(apiBase(), `${API_PREFIX}${path}${buildQuery(options.query)}`);
  const hasBody = body !== undefined;
  const isForm = body instanceof FormData;
  const doFetch = () =>
    fetch(url, {
      method,
      credentials: "include",
      headers: buildHeaders(method, hasBody && !isForm),
      body: hasBody ? (isForm ? body : JSON.stringify(body)) : undefined,
      signal: options.signal,
    });

  let response = await doFetch();
  // A missing/stale csrftoken cookie (fresh browser racing the boot prime,
  // cookie cleared mid-session) is recoverable: prime once and replay. Safe
  // because a middleware-rejected request never reached the view.
  if (UNSAFE_METHODS.has(method) && isCsrfReject(response) && (await primeCsrfCookie())) {
    response = await doFetch();
  }
  return handleResponse<T>(response);
}

export function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>("GET", path, undefined, options);
}

export interface BlobResponse {
  blob: Blob;
  /** From `Content-Disposition`; null when the server didn't name the file. */
  filename: string | null;
}

// RFC 6266. Django's `FileResponse` emits exactly one of the two — the plain
// parameter for an ASCII name, the extended one when that raises
// `UnicodeEncodeError` — but the extended form is checked first anyway,
// because it is the one that survives a non-ASCII name from any server that
// does send both.
function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const extended = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (extended) {
    try {
      return decodeURIComponent(extended[1]);
    } catch {
      // A malformed percent-escape isn't worth failing a download over —
      // fall through to the plain parameter.
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

/**
 * `GET` a binary body — a stored document streamed through the API (GAP-094).
 *
 * Deliberately not routed through `request`/`handleResponse`, which always
 * `.json()` the body. It still shares `throwIfNotOk`, so a 403/404/409 on a
 * blob route raises the same `ApiError` as everywhere else, and `Accept`
 * stays `application/json` so DRF's negotiation picks the JSON renderer for
 * those error bodies rather than 406-ing.
 */
export async function apiGetBlob(
  path: string,
  options: RequestOptions = {},
): Promise<BlobResponse> {
  const url = joinUrl(apiBase(), `${API_PREFIX}${path}${buildQuery(options.query)}`);
  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: buildHeaders("GET", false),
    signal: options.signal,
  });
  await throwIfNotOk(response);
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("content-disposition")),
  };
}

export function apiSend<T = void>(
  method: SendMethod,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  return request<T>(method, path, body, options);
}
