import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";

import {
  api,
  ApiError,
  setUnauthenticatedHandler,
  unwrap,
} from "../api/client";
import { keys } from "../api/queries";
import type { CurrentUser } from "../api/types";

interface AuthState {
  /** The signed-in account; null when signed out; undefined while still checking. */
  user: CurrentUser | null | undefined;
  signIn: (email: string, password: string) => Promise<CurrentUser>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/** Nothing cached for one account may show for the next. The sign-in query itself stays (it is
 * then set), since this provider is subscribed to it: removing it would leave a stale answer. */
function forgetOtherAccounts(client: QueryClient): void {
  client.removeQueries({
    predicate: (query) => query.queryKey[0] !== keys.me[0],
  });
}

async function whoAmI(): Promise<CurrentUser | null> {
  try {
    return unwrap(await api.GET("/v1/auth/me"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const me = useQuery({
    queryKey: keys.me,
    queryFn: whoAmI,
    staleTime: 5 * 60_000,
    retry: false,
  });

  useEffect(() => {
    // Any 401 means the sign-in ended (expired, revoked, password reset): show the sign-in page.
    setUnauthenticatedHandler(() => client.setQueryData(keys.me, null));
  }, [client]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const user = unwrap(
        await api.POST("/v1/auth/browser-session", {
          body: { email, password },
        }),
      );
      forgetOtherAccounts(client);
      client.setQueryData(keys.me, user);
      return user;
    },
    [client],
  );

  const signOut = useCallback(async () => {
    try {
      await api.DELETE("/v1/auth/browser-session");
    } finally {
      forgetOtherAccounts(client);
      client.setQueryData(keys.me, null);
    }
  }, [client]);

  const value = useMemo<AuthState>(
    () => ({
      user: me.isPending ? undefined : (me.data ?? null),
      signIn,
      signOut,
    }),
    [me.isPending, me.data, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** The signed-in account where there is one; undefined outside an AuthProvider (for parts, such
 * as the bots, that also appear where no one is signed in). */
export function useMaybeUser(): CurrentUser | null | undefined {
  return useContext(AuthContext)?.user;
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null)
    throw new Error("useAuth must be used inside <AuthProvider>");
  return state;
}
