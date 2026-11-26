import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_AVATAR, type Avatar } from "./avatar";
import { CompanionPicker } from "./CompanionPicker";

vi.mock("./BotFigure", () => ({
  BotFigure: ({ mode }: { mode: string }) => (
    <div data-testid="bot">{mode}</div>
  ),
}));

function Harness({
  start = DEFAULT_AVATAR,
  seen,
}: {
  start?: Avatar;
  seen: Avatar[];
}) {
  const [value, setValue] = useState(start);
  return (
    <CompanionPicker
      value={value}
      onChange={(next) => {
        seen.push(next);
        setValue(next);
      }}
    />
  );
}

describe("character creator", () => {
  it("builds a toy from parts, tab by tab, by keyboard", async () => {
    const seen: Avatar[] = [];
    render(<Harness seen={seen} />);
    const character = screen.getByRole("tab", { name: "Character" });
    character.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Shape" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await userEvent.click(screen.getByRole("radio", { name: "Tall" }));
    await userEvent.click(screen.getByRole("radio", { name: /Screen/ }));
    await userEvent.click(screen.getByRole("tab", { name: "Outfit" }));
    await userEvent.click(screen.getByRole("radio", { name: /Crown/ }));
    expect(seen.at(-1)).toMatchObject({
      body: "tall",
      head: "screen",
      hat: "crown",
    });
  });

  it("undoes and redoes changes", async () => {
    const seen: Avatar[] = [];
    render(<Harness seen={seen} />);
    await userEvent.click(screen.getByRole("tab", { name: "Shape" }));
    await userEvent.click(screen.getByRole("radio", { name: "Boxy" }));
    await userEvent.click(screen.getByRole("radio", { name: "Tall" }));
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(seen.at(-1)?.body).toBe("boxy");
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(seen.at(-1)?.body).toBe("round");
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Redo" }));
    expect(seen.at(-1)?.body).toBe("boxy");
  });

  it("warns when the eyes would be hard to see, and fixes it", async () => {
    const seen: Avatar[] = [];
    render(
      <Harness seen={seen} start={{ ...DEFAULT_AVATAR, glow: "#1a1a1a" }} />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Colours" }));
    expect(screen.getByRole("status")).toHaveTextContent("hard to see");
    await userEvent.click(
      screen.getByRole("button", { name: "Use a brighter glow" }),
    );
    expect(screen.queryByText(/hard to see/)).not.toBeInTheDocument();
    expect(seen.at(-1)?.glow).not.toBe("#1a1a1a");
  });

  it("explains that Pod and Rex keep their shape", async () => {
    render(
      <Harness seen={[]} start={{ ...DEFAULT_AVATAR, character: "rex" }} />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Face" }));
    expect(
      screen.getByText(/Rex keeps its own shape and face/),
    ).toBeInTheDocument();
  });

  it("strikes a pose in the preview", async () => {
    render(<Harness seen={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "Cheer" }));
    expect(screen.getByTestId("bot")).toHaveTextContent("celebrating");
    expect(screen.getByRole("button", { name: "Cheer" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
