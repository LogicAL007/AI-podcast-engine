import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "./AuthProvider";
import { RequireAuth, safeNext } from "./RequireAuth";

function LoginProbe() {
  const location = useLocation();
  return <p>login page {location.search}</p>;
}

function renderAt(path: string, me: { status: number; body: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(me.body), {
          status: me.status,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginProbe />} />
            <Route
              path="/shows"
              element={
                <RequireAuth>
                  <p>your shows</p>
                </RequireAuth>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireAuth", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends a signed-out visitor to sign in, remembering where they were going", async () => {
    renderAt("/shows?offset=20", { status: 401, body: { detail: "no token" } });
    expect(await screen.findByText(/login page/)).toHaveTextContent(
      `login page ?next=${encodeURIComponent("/shows?offset=20")}`,
    );
  });

  it("shows the page to a signed-in user", async () => {
    renderAt("/shows", {
      status: 200,
      body: {
        user_id: "u",
        email: "a@b.c",
        role: "admin",
        token_id: "t",
        token_kind: "session",
        expires_at: "2027-01-01T00:00:00Z",
      },
    });
    expect(await screen.findByText("your shows")).toBeInTheDocument();
  });

  it("only returns to pages of this app after signing in", () => {
    expect(safeNext("/shows/1")).toBe("/shows/1");
    expect(safeNext("https://evil.example")).toBe("/shows");
    expect(safeNext("//evil.example")).toBe("/shows");
    expect(safeNext(null)).toBe("/shows");
  });
});
