import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { LoginPage } from "./LoginPage";

/** Signed out, with the given setup answer from the server. */
function serve(setup: Record<string, boolean>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(String(input), init);
      const path = new URL(request.url, "http://localhost").pathname;
      const [status, body] = path.endsWith("/v1/auth/setup")
        ? [200, { first_account_open: false, signup_open: false, ...setup }]
        : [401, { detail: "the token is missing" }];
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LoginPage", () => {
  it("offers Google first when the server has it, keeping where to go next", async () => {
    serve({ google_sign_in: true });
    renderAt("/login?next=%2Fshows%2F7");
    const google = await screen.findByRole("link", {
      name: "Sign in with Google",
    });
    expect(google).toHaveAttribute(
      "href",
      "/api/v1/auth/google/start?next=%2Fshows%2F7",
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "About Podcast Engine" }),
    ).toBeInTheDocument();
  });

  it("has no Google button when the server does not offer it", async () => {
    serve({ google_sign_in: false });
    renderAt("/login");
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Sign in with Google" }),
    ).not.toBeInTheDocument();
  });

  it("explains why a Google sign-in came back", async () => {
    serve({ google_sign_in: true });
    renderAt("/login?google=no_account");
    expect(
      await screen.findByText(/No account uses that Google address/),
    ).toBeInTheDocument();
  });
});
