import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { OnboardingPage } from "./OnboardingPage";
import { SignUpPage } from "./SignUpPage";

const ADA = {
  user_id: "u",
  email: "ada@example.org",
  role: "creator",
  token_id: "t",
  token_kind: "session",
  expires_at: "2027-04-01T00:00:00Z",
};

type Handler = (
  method: string,
  path: string,
  body: unknown,
) => { status: number; body: unknown };

/** Stub fetch with a tiny router over /api/v1 paths; returns the requests made. */
function serve(handler: Handler) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(String(input), init);
      const path = new URL(request.url, "http://localhost").pathname.replace(
        "/api",
        "",
      );
      const text = request.method === "GET" ? "" : await request.text();
      const body = text ? JSON.parse(text) : null;
      calls.push({ method: request.method, path, body });
      const reply = handler(request.method, path, body);
      return new Response(JSON.stringify(reply.body), {
        status: reply.status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

function Probe() {
  const location = useLocation();
  return <p>at {location.pathname + location.search}</p>;
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
            <Route path="/signup" element={<SignUpPage />} />
            <Route path="/welcome" element={<OnboardingPage />} />
            <Route path="*" element={<Probe />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("sign-up page", () => {
  it("says sign-up is closed when the server does not allow it", async () => {
    serve((_, path) =>
      path === "/v1/auth/setup"
        ? {
            status: 200,
            body: { first_account_open: false, signup_open: false },
          }
        : { status: 401, body: { detail: "no token" } },
    );
    renderAt("/signup");
    expect(
      await screen.findByText(/Sign-up is closed on this server/),
    ).toBeInTheDocument();
  });

  it("creates a creator account, signs in and starts onboarding", async () => {
    const user = userEvent.setup({ delay: null });
    let signedIn = false;
    const calls = serve((method, path) => {
      if (path === "/v1/auth/setup")
        return {
          status: 200,
          body: { first_account_open: false, signup_open: true },
        };
      if (path === "/v1/auth/register")
        return {
          status: 201,
          body: { ...ADA, created_at: "2026-10-24T09:00:00Z", disabled: false },
        };
      if (path === "/v1/auth/browser-session" && method === "POST") {
        signedIn = true;
        return { status: 200, body: ADA };
      }
      if (path === "/v1/auth/me")
        return signedIn
          ? { status: 200, body: ADA }
          : { status: 401, body: { detail: "no token" } };
      return { status: 404, body: { detail: "not found" } };
    });
    renderAt("/signup");
    await user.type(await screen.findByLabelText("Email"), "ada@example.org");
    await user.type(
      screen.getByLabelText(/^Password/),
      "a long enough passphrase",
    );
    await user.type(
      screen.getByLabelText("Confirm password"),
      "a long enough passphrase",
    );
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(
      await screen.findByRole("heading", { name: "Welcome, ada" }),
    ).toBeInTheDocument();
    const register = calls.find((call) => call.path === "/v1/auth/register");
    expect(register?.body).toMatchObject({
      email: "ada@example.org",
      role: "creator",
    });
  });
});

describe("onboarding", () => {
  it("walks four steps, saves the chosen bot, and ends on the sample show", async () => {
    const calls = serve((method, path, body) => {
      if (path === "/v1/auth/me") return { status: 200, body: ADA };
      if (path === "/v1/auth/me/avatar" && method === "PUT")
        return { status: 200, body: { ...ADA, avatar: body } };
      return { status: 404, body: { detail: "not found" } };
    });
    renderAt("/welcome");
    expect(
      await screen.findByRole("heading", { name: "Welcome, ada" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("heading", { name: "Meet your companion" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Rex/ }));
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Rexie");
    await userEvent.click(screen.getByRole("tab", { name: "Outfit" }));
    await userEvent.click(screen.getByRole("radio", { name: "Headphones" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("heading", { name: "How an episode is made" }),
    ).toBeInTheDocument();
    const saved = calls.find((call) => call.path === "/v1/auth/me/avatar");
    expect(saved?.body).toMatchObject({
      character: "rex",
      hat: "headphones",
      name: "Rexie",
    });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("heading", { name: "Make your first show" }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Try the sample/ }),
    );
    expect(
      await screen.findByText("at /shows/new?sample=1"),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("pe.welcome.skipped")).toBe("1");
  });

  it("can be skipped from any step", async () => {
    serve((_, path) =>
      path === "/v1/auth/me"
        ? { status: 200, body: ADA }
        : { status: 404, body: { detail: "not found" } },
    );
    renderAt("/welcome?step=2");
    await userEvent.click(await screen.findByRole("button", { name: "Skip" }));
    expect(await screen.findByText("at /shows")).toBeInTheDocument();
  });
});
