import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WaveformPlayer } from "../../components/WaveformPlayer";
import { NewVoicePage } from "./NewVoicePage";

afterEach(() => vi.unstubAllGlobals());

const CONSENT = {
  version: "2026-10-31",
  title: "Voice recording and voice cloning consent form",
  sections: [
    { heading: "1. About this form", paragraphs: ["I agree to be cloned."] },
    {
      heading: "11. Withdrawing consent",
      paragraphs: [
        "When the voice is deleted:",
        "- the recording is deleted;",
        "- no new episode uses it.",
        "Finished episodes keep their audio.",
      ],
    },
  ],
  statement: "Voice recording and voice cloning consent form ...",
  pdf: "/v1/voices/consent.pdf",
};

function renderPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(CONSENT), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
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
      screen.getByLabelText(
        "I have read the consent form above and agree to it.",
      ),
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

  it("shows the whole form as a document, with the same form as a PDF", async () => {
    renderPage();
    const form = await screen.findByRole("document", {
      name: /consent form, version 2026-10-31/,
    });
    expect(form).toHaveTextContent("1. About this form");
    expect(form).toHaveTextContent("11. Withdrawing consent");
    // "- " paragraphs read as one bulleted list, between the ordinary paragraphs.
    expect(
      within(form)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["the recording is deleted;", "no new episode uses it."]);
    expect(screen.getByRole("link", { name: "Open the PDF" })).toHaveAttribute(
      "href",
      "/api/v1/voices/consent.pdf",
    );
  });

  it("asks for agreement only once the form has been read to the end", async () => {
    // jsdom does no layout: give the form a height taller than its box.
    const sizes = { scrollHeight: 900, clientHeight: 300 };
    const spies = Object.entries(sizes).map(([name, value]) =>
      vi
        .spyOn(HTMLElement.prototype, name as "scrollHeight", "get")
        .mockReturnValue(value),
    );
    try {
      renderPage();
      const form = await screen.findByRole("document");
      const agree = screen.getByLabelText(
        "I have read the consent form above and agree to it.",
      );
      expect(agree).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Agree and continue" }),
      ).toBeDisabled();
      expect(
        screen.getByText("Scroll to the end of the form to continue."),
      ).toBeInTheDocument();

      form.scrollTop = 600; // the bottom: 600 + 300 = 900
      fireEvent.scroll(form);
      expect(agree).toBeEnabled();
      expect(
        screen.getByText("You have read the whole form."),
      ).toBeInTheDocument();
    } finally {
      spies.forEach((spy) => spy.mockRestore());
    }
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
