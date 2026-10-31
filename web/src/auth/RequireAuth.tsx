import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { Spinner } from "../components/Spinner";
import { useAuth } from "./AuthProvider";

/** Shows its children to a signed-in user; anyone else goes to sign in and comes back after. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) {
    return (
      <div className="public-page">
        <Spinner label="Checking your sign-in" />
      </div>
    );
  }
  if (user === null) {
    const back = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(back)}`} replace />;
  }
  return <>{children}</>;
}

/** Where to go after signing in: the page the user wanted, if it is one of ours. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
