// The assistant on every page: each page tells the bot what is going on there (useAssistant), and
// the one dock in the app shell shows it: the bot, its line or first-time hint, buttons for the
// next steps, a chat, and a guided tour. Actions are plain functions the page already has (a
// mutation, a navigation), so the bot can only do what the page's own buttons do.
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { components } from "../api/schema";
import type { BotMode } from "./botMode";

export type AssistantPage = components["schemas"]["Question"]["page"];
export type ActionId = components["schemas"]["Answer"]["actions"][number];

export interface BotAction {
  /** One of the API's action ids, so a chat answer can point at it, or any page-only id. */
  id: ActionId | string;
  label: string;
  run: () => unknown;
  /** Offered only when a chat answer points at it, not as a standing button. */
  hidden?: boolean;
  /** Ask first: for anything that spends quota or cannot be undone. */
  confirm?: {
    title: string;
    body: string;
    confirmLabel: string;
    danger?: boolean;
  };
}

export interface TourStep {
  /** The `data-tour` value of the element to point at; missing ones are skipped. */
  target: string;
  title: string;
  text: string;
}

export interface PageAssist {
  page: AssistantPage;
  /** Remembers this place: whether its dock was closed, and whether its tour was taken. */
  key: string;
  /** Which first-time hint this is; each is shown once, then the short line. */
  moment: string;
  mode: BotMode;
  line: string;
  hint?: string;
  actions?: BotAction[];
  questions?: string[];
  tour?: TourStep[];
  episodeId?: string;
  showId?: string;
}

interface AssistantState {
  assist: PageAssist | null;
  set: (assist: PageAssist | null) => void;
  /** The latest action functions (they change every render; the rest of the assist does not). */
  actions: React.RefObject<BotAction[]>;
}

const Context = createContext<AssistantState | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [assist, set] = useState<PageAssist | null>(null);
  const actions = useRef<BotAction[]>([]);
  const value = useMemo(() => ({ assist, set, actions }), [assist]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAssistantState(): AssistantState | null {
  return useContext(Context);
}

/** Tell the bot about this page. Pass null while the page is still loading. */
export function useAssistant(assist: PageAssist | null): void {
  const state = useContext(Context);
  if (state) state.actions.current = assist?.actions ?? [];
  // Re-register only when something the dock shows changes, not on every render.
  const signature = assist
    ? JSON.stringify({
        ...assist,
        actions: assist.actions?.map((a) => [a.id, a.label, a.hidden]),
      })
    : "";
  const set = state?.set;
  useEffect(() => {
    if (!set) return;
    // The dock takes the functions from `actions`; this copy only says which are offered.
    set(
      signature
        ? { ...(JSON.parse(signature) as PageAssist), actions: undefined }
        : null,
    );
    return () => set(null);
  }, [set, signature]);
}
