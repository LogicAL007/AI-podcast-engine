import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RefreshDialog } from "./RefreshDialog";

afterEach(() => vi.unstubAllGlobals());

function renderDialog() {
  const bodies: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const text = await request.text();
      bodies.push(text ? JSON.parse(text) : null);
      return new Response(
        JSON.stringify({ episode_id: "e2", show_id: "s1", status: "queued" }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      );
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/episodes/e1"]}>
        <Routes>
          <Route
            path="/episodes/e1"
            element={<RefreshDialog showId="s1" open onClose={() => {}} />}
          />
          <Route path="/episodes/e2" element={<p>The new revision</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return bodies;
}

// jsdom has no showModal, so the dialog stays closed and its contents count as hidden.
const hidden = true;

describe("refreshing an episode", () => {
  it("redoes only what changed by default, then opens the new revision", async () => {
    const bodies = renderDialog();
    expect(
      screen.getByRole("radio", { name: /Only what changed/, hidden }),
    ).toBeChecked();
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh it", hidden }),
    );
    expect(await screen.findByText("The new revision")).toBeInTheDocument();
    expect(bodies).toEqual([null]); // no body: the API's default refresh
  });

  it("can rebuild every segment", async () => {
    const bodies = renderDialog();
    await userEvent.click(
      screen.getByRole("radio", { name: /Everything, from scratch/, hidden }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Rebuild it", hidden }),
    );
    expect(await screen.findByText("The new revision")).toBeInTheDocument();
    expect(bodies).toEqual([{ rebuild: true }]);
  });
});
