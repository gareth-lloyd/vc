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

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    authChannel.emitUnauthorized();
    throw new ApiError(401, await parseErrorBody(response));
  }
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response));
  }
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
  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: buildHeaders(method, hasBody && !isForm),
    body: hasBody ? (isForm ? body : JSON.stringify(body)) : undefined,
    signal: options.signal,
  });
  return handleResponse<T>(response);
}

export function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>("GET", path, undefined, options);
}

export function apiSend<T = void>(
  method: SendMethod,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  return request<T>(method, path, body, options);
}
