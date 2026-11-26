import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRememberedFlag } from "../../hooks/useRememberedFlag";
import { Welcome } from "./Welcome";

describe("first-run welcome", () => {
  it("lists the three steps and links to a new show", () => {
    render(
      <MemoryRouter>
        <Welcome onSkip={() => {}} />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Let's make your first episode" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(
      screen.getByRole("link", { name: "Create your first show" }),
    ).toHaveAttribute("href", "/shows/new");
  });

  it("can be skipped", async () => {
    const onSkip = vi.fn();
    render(
      <MemoryRouter>
        <Welcome onSkip={onSkip} />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Skip the tour" }),
    );
    expect(onSkip).toHaveBeenCalled();
  });
});

describe("remembered flags", () => {
  afterEach(() => window.localStorage.clear());

  it("survives a remount through local storage", () => {
    const first = renderHook(() => useRememberedFlag("pe.test"));
    act(() => first.result.current[1](true));
    first.unmount();
    expect(
      renderHook(() => useRememberedFlag("pe.test")).result.current[0],
    ).toBe(true);
  });

  it("reads a new key afresh instead of keeping the old answer", () => {
    window.localStorage.setItem("pe.a", "1");
    const { result, rerender } = renderHook(
      ({ key }) => useRememberedFlag(key),
      {
        initialProps: { key: "pe.a" },
      },
    );
    expect(result.current[0]).toBe(true);
    rerender({ key: "pe.b" });
    expect(result.current[0]).toBe(false);
  });

  it("still works in memory when storage is blocked", () => {
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("blocked");
      });
    const { result } = renderHook(() => useRememberedFlag("pe.blocked"));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    spy.mockRestore();
  });
});
