import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { HomePage } from "./HomePage";

const page = (items: unknown[]) => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
  links: {},
});

const SHOW = {
  show_id: "s1",
  topic: "How the Moon makes the tides",
  sources: ["https://en.wikipedia.org/wiki/Tide"],
  created_at: "2026-10-01T10:00:00Z",
};
const EPISODES = [
  {
    episode_id: "e1",
    show_id: "s1",
    status: "published",
    revision: 1,
    created_at: "2026-10-02T10:00:00Z",
    published_at: "2026-10-02T11:00:00Z",
  },
  {
    episode_id: "e2",
    show_id: "s1",
    status: "needs_review",
    revision: 2,
    created_at: "2026-10-20T10:00:00Z",
    published_at: null,
  },
];
const VOICE = {
  voice_id: "v1",
  name: "My voice",
  speaker: "Ada",
  created_at: "2026-10-05T10:00:00Z",
};

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(String(input), init);
      const url = new URL(request.url, "http://localhost");
      const body = url.pathname.endsWith("/v1/shows")
        ? page([SHOW])
        : url.pathname.endsWith("/v1/voices")
          ? page([VOICE])
          : url.pathname.endsWith("/v1/episodes")
            ? page(
                url.searchParams.get("status") === "needs_review"
                  ? [EPISODES[1]]
                  : EPISODES,
              )
            : {};
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function renderHome() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <HomePage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HomePage", () => {
  it("lists recent episodes, shows and voices, newest first", async () => {
    serve();
    renderHome();
    const table = await screen.findByRole("table");
    const titles = within(table)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(titles).toEqual([
      "How the Moon makes the tides · episode 2",
      "My voice",
      "How the Moon makes the tides · episode 1",
      "How the Moon makes the tides",
    ]);
    expect(within(table).getByText("Needs review")).toBeInTheDocument();
  });

  it("points the review card at the waiting episode", async () => {
    serve();
    renderHome();
    const card = await screen.findByRole("link", {
      name: /1 episode waiting for you/,
    });
    expect(card).toHaveAttribute("href", "/episodes/e2");
  });

  it("filters by search and tab, and sorts by a column", async () => {
    serve();
    const user = userEvent.setup();
    renderHome();
    await screen.findByRole("table");
    await user.type(screen.getByRole("searchbox"), "voice");
    expect(screen.getByRole("heading", { name: /Results for/ })).toBeVisible();
    expect(within(screen.getByRole("table")).getAllByRole("link")).toHaveLength(
      1,
    );
    await user.clear(screen.getByRole("searchbox"));
    await user.click(screen.getByRole("tab", { name: "Shows" }));
    expect(within(screen.getByRole("table")).getAllByRole("link")).toHaveLength(
      1,
    );
    await user.click(screen.getByRole("tab", { name: "All" }));
    await user.click(screen.getByRole("button", { name: /Title/ }));
    expect(screen.getByRole("columnheader", { name: /Title/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
  });

  it("opens a template as a filled-in new show", async () => {
    serve();
    renderHome();
    expect(
      await screen.findByRole("link", { name: /This week at NASA/ }),
    ).toHaveAttribute("href", "/shows/new?template=nasa");
  });
});
