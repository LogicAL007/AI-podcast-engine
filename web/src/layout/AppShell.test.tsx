import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { AppShell } from "./AppShell";

function renderShell(path: string, narrow = false) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({
        matches: narrow,
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            user_id: "u",
            email: "ada@example.org",
            role: "creator",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="*" element={<p>page</p>} />
            </Route>
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

describe("sidebar", () => {
  it("holds the main places, quick actions and the account", async () => {
    renderShell("/episodes/e1");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveTextContent("Shows");
    expect(screen.getByRole("link", { name: /Shows/ })).toHaveAttribute(
      "aria-current",
      "page",
    ); // inside an episode
    expect(screen.getByRole("link", { name: /Voice studio/ })).toHaveAttribute(
      "href",
      "/voices",
    );
    expect(screen.getByRole("link", { name: /New show/ })).toHaveAttribute(
      "href",
      "/shows/new",
    );
    expect(screen.getByRole("link", { name: /Add a voice/ })).toHaveAttribute(
      "href",
      "/voices/new",
    );
    expect(await screen.findByText("ada@example.org")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign out" }),
    ).toBeInTheDocument();
  });

  it("is a drawer on narrow screens: opened by the menu button, closed by Escape", async () => {
    const user = userEvent.setup({ delay: null });
    renderShell("/shows", true);
    const sidebar = screen.getByRole("complementary", {
      name: "Sidebar",
      hidden: true,
    });
    expect(sidebar).toHaveAttribute("inert");
    const menu = screen.getByRole("button", { name: "Open the menu" });
    await user.click(menu);
    expect(sidebar).not.toHaveAttribute("inert");
    expect(menu).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(sidebar).toHaveAttribute("inert");
    expect(menu).toHaveFocus();
  });

  it("collapses to an icon rail that keeps every name, and remembers it", async () => {
    const user = userEvent.setup({ delay: null });
    renderShell("/shows");
    await user.click(
      screen.getByRole("button", { name: "Collapse the sidebar" }),
    );
    const toggle = screen.getByRole("button", { name: "Expand the sidebar" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector(".app-layout")).toHaveClass(
      "sidebar-collapsed",
    );
    // Labels are hidden from sight only: screen readers still hear every link.
    expect(screen.getByRole("link", { name: /Voice studio/ })).toHaveAttribute(
      "title",
      "Voice studio",
    );
    expect(
      screen.getByRole("button", { name: "Sign out" }),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("pe.sidebar.collapsed")).toBe("1");
    await user.click(toggle);
    expect(document.querySelector(".app-layout")).not.toHaveClass(
      "sidebar-collapsed",
    );
  });
});
