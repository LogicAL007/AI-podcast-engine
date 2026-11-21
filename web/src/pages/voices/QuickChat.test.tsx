import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  CHAT_LENGTH,
  CHAT_QUESTIONS,
  pickQuestions,
  QuickChat,
} from "./QuickChat";

describe("QuickChat", () => {
  it("picks a different set of distinct questions for each take", () => {
    const set = pickQuestions(() => 0.1);
    expect(set).toHaveLength(CHAT_LENGTH);
    expect(new Set(set).size).toBe(CHAT_LENGTH);
    expect(
      set.every((q) => (CHAT_QUESTIONS as readonly string[]).includes(q)),
    ).toBe(true);
    expect(pickQuestions(() => 0.9)).not.toEqual(set);
  });

  it("waits for the recording, then moves through the questions to the last one", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<QuickChat recording={false} round={0} />);
    expect(screen.getByText("Question 1 of 3")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Next question/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Start recording, then answer/),
    ).toBeInTheDocument();

    rerender(<QuickChat recording round={0} />);
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    expect(screen.getByText("Question 2 of 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    expect(screen.getByText("Question 3 of 3")).toBeInTheDocument();
    expect(screen.getByText(/Last one/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Next question/ }),
    ).not.toBeInTheDocument();

    rerender(<QuickChat recording round={1} />); // "Record again": back to the first question
    expect(screen.getByText("Question 1 of 3")).toBeInTheDocument();
  });
});
