// The typed API client. Types come from the API's own OpenAPI description (npm run gen:api).
//
// Sign-in is a cookie the page cannot read (HttpOnly). Requests that change something must send
// the CSRF token from the readable pe_csrf cookie in the X-CSRF-Token header; this client does
// that for every unsafe method.
import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

export const API_BASE = "/api";
export const CSRF_COOKIE = "pe_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

/** An error the API answered with: its status and its `detail` message. */
export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter: number | null;

  constructor(
    status: number,
    message: string,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function readCookie(
  name: string,
  source: string = document.cookie,
): string | null {
  for (const part of source.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

/** The message to show for an error body: FastAPI sends a string, or a list for 422s. */
export function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string };
          const field = entry.loc?.filter((part) => part !== "body").join(".");
          return field ? `${field}: ${entry.msg ?? ""}` : (entry.msg ?? "");
        })
        .join("; ");
    }
  }
  return fallback;
}

let onUnauthenticated: () => void = () => {};

/** Called when a request comes back 401, so the app can send the user to sign in. */
export function setUnauthenticatedHandler(handler: () => void): void {
  onUnauthenticated = handler;
}

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE.has(request.method)) {
      const token = readCookie(CSRF_COOKIE);
      if (token) request.headers.set(CSRF_HEADER, token);
    }
    return request;
  },
};

export const errorMiddleware: Middleware = {
  async onResponse({ response, request }) {
    if (response.ok) return response;
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      body = null;
    }
    const signingIn = new URL(
      request.url,
      window.location.origin,
    ).pathname.endsWith("/auth/browser-session");
    if (response.status === 401 && !signingIn) onUnauthenticated();
    const retry = response.headers.get("Retry-After");
    throw new ApiError(
      response.status,
      detailOf(
        body,
        `The request failed (${response.status} ${response.statusText}).`,
      ),
      retry ? Number(retry) : null,
    );
  },
};

export const api = createClient<paths>({
  // Absolute, on this page's own origin: some Request implementations reject relative URLs.
  baseUrl: `${window.location.origin}${API_BASE}`,
  credentials: "same-origin",
  // Looked up on each call (not captured once), so tests and polyfills can replace fetch.
  fetch: (request) => globalThis.fetch(request),
});
api.use(csrfMiddleware, errorMiddleware);

/** Unwrap an openapi-fetch result: errors are already thrown by the middleware above. */
export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.data === undefined) {
    if (result.response.status === 204) return undefined as T;
    throw new ApiError(
      result.response.status,
      "The API sent an empty response.",
    );
  }
  return result.data;
}
