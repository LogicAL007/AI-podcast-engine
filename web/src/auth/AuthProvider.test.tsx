import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { messageOf } from "../components/Alert";
import { AuthProvider, useAuth } from "./AuthProvider";

const USER = {
  user_id: "u1",
  email: "ada@example.org",
  role: "admin",
  token_id: "t1",
  token_kind: "session",
  expires_at: "2027-04-20T00:00:00Z",
};

function Probe() {
  const { user, signIn, signOut } = useAuth();
  return (
    <div>
      <p>
        user: {user === undefined ? "checking" : (user?.email ?? "signed out")}
      </p>
      <button
        onClick={() => void signIn("ada@example.org", "a long passphrase")}
      >
        in
      </button>
      <button onClick={() => void signOut()}>out</button>
    </div>
  );
}

function respond(status: number, body: unknown = null) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("AuthProvider", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is signed in right after signing in, and out right after signing out", async () => {
    // Regression: clearing the whole query cache on sign-in left the provider on a stale query.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        const path = new URL(request.url).pathname;
        if (path.endsWith("/auth/me"))
          return respond(401, { detail: "no token" });
        if (path.endsWith("/auth/browser-session")) {
          return request.method === "POST" ? respond(200, USER) : respond(204);
        }
        return respond(404, { detail: "not found" });
      }),
    );
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("user: signed out")).toBeInTheDocument();
    await act(async () => screen.getByText("in").click());
    await waitFor(() =>
      expect(screen.getByText("user: ada@example.org")).toBeInTheDocument(),
    );
    await act(async () => screen.getByText("out").click());
    await waitFor(() =>
      expect(screen.getByText("user: signed out")).toBeInTheDocument(),
    );
  });

  it("shows the API's messages as sentences", () => {
    expect(messageOf(new ApiError(401, "wrong email or password"))).toBe(
      "Wrong email or password.",
    );
    expect(messageOf(new ApiError(429, "slow down", 120))).toBe(
      "Slow down. Try again in about 2 minute(s).",
    );
  });
});
