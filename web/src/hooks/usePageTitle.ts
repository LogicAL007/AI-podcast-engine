import { useEffect } from "react";

export const APP_NAME = "Oasis";

/** Names the browser tab after the page, so tabs, history and screen readers say where you are. */
export function usePageTitle(title: string | null | undefined): void {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}
