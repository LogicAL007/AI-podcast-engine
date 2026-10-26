import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  csrfMiddleware,
  CSRF_HEADER,
  detailOf,
  errorMiddleware,
  readCookie,
  setUnauthenticatedHandler,
} from "./client";

type Hook = (args: { request: Request; response?: Response }) => unknown;
const onRequest = csrfMiddleware.onRequest as unknown as Hook;
const onResponse = errorMiddleware.onResponse as unknown as Hook;

describe("CSRF header", () => {
  it("is sent with changes, from the readable cookie", async () => {
    document.cookie = "pe_csrf=abc123; path=/";
    const request = (await onRequest({
      request: new Request("http://x/api/v1/shows", { method: "POST" }),
    })) as Request;
    expect(request.headers.get(CSRF_HEADER)).toBe("abc123");
  });

  it("is not sent with reads", async () => {
    document.cookie = "pe_csrf=abc123; path=/";
    const request = (await onRequest({
      request: new Request("http://x/api/v1/shows"),
    })) as Request;
    expect(request.headers.get(CSRF_HEADER)).toBeNull();
  });

  it("reads one cookie among several", () => {
    expect(readCookie("pe_csrf", "a=1; pe_csrf=t%3D1; b=2")).toBe("t=1");
    expect(readCookie("missing", "a=1")).toBeNull();
  });
});

describe("errors", () => {
  const json = (
    status: number,
    body: unknown,
    headers: Record<string, string> = {},
  ) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", ...headers },
    });

  it("become ApiError with the API's message", async () => {
    const request = new Request("http://x/api/v1/shows/1");
    await expect(
      onResponse({
        request,
        response: json(404, { detail: "show 1 not found" }),
      }),
    ).rejects.toEqual(new ApiError(404, "show 1 not found"));
  });

  it("send the user to sign in on 401, except when signing in fails", async () => {
    const handler = vi.fn();
    setUnauthenticatedHandler(handler);
    await expect(
      onResponse({
        request: new Request("http://x/api/v1/shows"),
        response: json(401, { detail: "no" }),
      }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
    await expect(
      onResponse({
        request: new Request("http://x/api/v1/auth/browser-session", {
          method: "POST",
        }),
        response: json(401, { detail: "wrong email or password" }),
      }),
    ).rejects.toThrow("wrong email or password");
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("carry Retry-After for 429", async () => {
    const error = await (
      onResponse({
        request: new Request("http://x/api/v1/auth/browser-session", {
          method: "POST",
        }),
        response: json(429, { detail: "slow down" }, { "Retry-After": "120" }),
      }) as Promise<unknown>
    ).catch((e: unknown) => e);
    expect((error as ApiError).retryAfter).toBe(120);
  });

  it("list each problem of a validation error", () => {
    const body = {
      detail: [
        { loc: ["body", "topic"], msg: "too short" },
        { loc: ["body"], msg: "bad" },
      ],
    };
    expect(detailOf(body, "x")).toBe("topic: too short; bad");
    expect(detailOf(null, "fallback")).toBe("fallback");
  });
});
