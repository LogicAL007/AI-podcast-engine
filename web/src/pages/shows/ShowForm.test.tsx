import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ShowForm } from "./ShowForm";
import { EMPTY_SHOW, languageOptions } from "./showValues";

function wizard(onSubmit = vi.fn()) {
  render(
    <ShowForm
      wizard
      initial={EMPTY_SHOW}
      submitLabel="Create show"
      busy={false}
      error={null}
      onSubmit={onSubmit}
    />,
  );
  return onSubmit;
}

describe("new show wizard", () => {
  it("asks for the topic before moving on", async () => {
    wizard();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Use 3 to 200 characters.")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "What is the show about?" }),
    ).toBeInTheDocument();
  });

  it("needs only a topic, sending the defaults for the rest", async () => {
    const onSubmit = wizard();
    await userEvent.type(screen.getByLabelText(/Topic/), "Tides and the moon");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("heading", { name: "How should it sound?" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create show" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        topic: "Tides and the moon",
        language: "en",
        target_minutes: 7,
        sources: [],
      }),
    );
  });

  it("sends searches, one per line, tidied", async () => {
    const onSubmit = wizard();
    await userEvent.type(screen.getByLabelText(/Topic/), "Tides and the moon");
    await userEvent.type(
      screen.getByLabelText(/Searches/),
      "  ocean   tides {enter}{enter}moon phases",
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Create show" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        search_queries: ["ocean tides", "moon phases"],
      }),
    );
  });

  it("allows at most three searches", async () => {
    wizard();
    await userEvent.type(screen.getByLabelText(/Topic/), "Tides and the moon");
    await userEvent.type(
      screen.getByLabelText(/Searches/),
      "one{enter}two{enter}three{enter}four",
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("At most 3 searches.")).toBeInTheDocument();
  });

  it("keeps what was typed when going back", async () => {
    wizard();
    await userEvent.type(screen.getByLabelText(/Topic/), "Bridges");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText(/Topic/)).toHaveValue("Bridges");
  });

  it("opens More options when a field in it needs fixing", async () => {
    const onSubmit = wizard();
    await userEvent.type(screen.getByLabelText(/Topic/), "Bridges");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    const segments = screen.getByLabelText("Most segments per episode");
    await userEvent.clear(segments);
    await userEvent.type(segments, "99");
    await userEvent.click(screen.getByRole("button", { name: "Create show" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("More options").closest("details")).toHaveAttribute(
      "open",
    );
  });
});

describe("sample show", () => {
  it("fills a ready topic and open-licence sources", async () => {
    const onSubmit = wizard();
    await userEvent.click(screen.getByRole("button", { name: "Try a sample" }));
    expect(screen.getByLabelText(/Topic/)).toHaveValue(
      "How the Moon makes the tides",
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Create show" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        sources: [
          "https://en.wikipedia.org/wiki/Tide",
          "https://en.wikipedia.org/wiki/Tidal_force",
        ],
        attribution: expect.stringContaining("CC BY-SA 4.0"),
      }),
    );
  });
});

describe("language choices", () => {
  it("keeps a saved language that is not in the list", () => {
    expect(languageOptions("it").at(-1)).toEqual({ value: "it", label: "it" });
    expect(
      languageOptions("fr-CA").some((option) => option.value === "it"),
    ).toBe(false);
  });
});
