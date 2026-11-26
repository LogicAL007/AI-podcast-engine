import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DEFAULT_AVATAR } from "./avatar";
import { BotFigure } from "./BotFigure";

describe("interactive bot", () => {
  it("is a button that answers a tap or Enter with something to say", async () => {
    render(
      <BotFigure
        mode="greeting"
        avatar={{ ...DEFAULT_AVATAR, name: "Pip" }}
        interactive
      />,
    );
    const bot = screen.getByRole("button", {
      name: "Pip, your assistant. Press to say hi.",
    });
    bot.focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("status")).toHaveTextContent("Hi! I'm Pip.");
    await userEvent.keyboard(" ");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Beep boop! Tap me again.",
    );
  });

  it("is decoration when not interactive", () => {
    render(<BotFigure mode="working" avatar={DEFAULT_AVATAR} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
