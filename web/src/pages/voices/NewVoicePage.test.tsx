import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WaveformPlayer } from "../../components/WaveformPlayer";
import { NewVoicePage } from "./NewVoicePage";

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            version: "2026-10-25",
            statement: "I agree to be cloned.",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
    ),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <NewVoicePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("adding a voice", () => {
  it("will not record anything until the consent form is complete", async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    expect(
      await screen.findByText("I agree to be cloned."),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Agree and continue" }),
    );
    expect(
      screen.getByText("Agree to all three statements to continue."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Consent" }),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Your full name"), "Ada Lovelace");
    await user.click(
      screen.getByLabelText("I agree to the consent statement above."),
    );
    await user.click(screen.getByLabelText(/labelled as AI-generated/));
    await user.click(screen.getByLabelText(/withdraw consent/));
    await user.type(screen.getByLabelText("Signature"), "Ada Lovelace");
    await user.click(
      screen.getByRole("button", { name: "Agree and continue" }),
    );
    expect(
      screen.getByRole("heading", { name: "Record or upload" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start recording" }),
    ).toBeInTheDocument();
  });

  it("asks where the written permission is kept for someone else's voice", async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await screen.findByText("I agree to be cloned.");
    await user.click(
      screen.getByRole("radio", { name: /Someone else's voice/ }),
    );
    expect(screen.getByLabelText("Their full name")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Where is their written permission kept?"),
    ).toBeInTheDocument();
  });
});

describe("waveform player", () => {
  it("is a labelled slider with a play button", () => {
    render(<WaveformPlayer blob={new Blob([])} title="Episode 2 audio" />);
    expect(
      screen.getByRole("slider", { name: "Episode 2 audio: position" }),
    ).toHaveAttribute("aria-valuetext", "0:00 of 0:00");
    expect(
      screen.getByRole("button", { name: "Play Episode 2 audio" }),
    ).toBeInTheDocument();
  });
});
