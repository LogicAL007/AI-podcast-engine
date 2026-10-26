import { useCallback, useState } from "react";

// Per-viewer conveniences (a skipped welcome, a closed dock, a dismissed hint) kept in this
// browser only. Storage can be missing or blocked, so every access is guarded and the app
// works the same without it: the flag then lasts until the page reloads.
function read(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function write(key: string, value: boolean): void {
  try {
    if (value) window.localStorage.setItem(key, "1");
    else window.localStorage.removeItem(key);
  } catch {
    // Storage unavailable: keep the flag in memory only.
  }
}

/** A yes/no remembered in this browser under `key`. A new key (say, the next moment of an
 * episode) is read afresh rather than inheriting the old key's answer. */
export function useRememberedFlag(
  key: string,
): [boolean, (value: boolean) => void] {
  const [state, setState] = useState(() => ({ key, flag: read(key) }));
  if (state.key !== key) setState({ key, flag: read(key) });
  const set = useCallback(
    (value: boolean) => {
      write(key, value);
      setState({ key, flag: value });
    },
    [key],
  );
  return [state.key === key ? state.flag : read(key), set];
}
