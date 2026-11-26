import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useConfirmPasswordReset } from "../api/queries";
import { ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { TextField } from "../components/Field";
import { PublicLayout } from "../layout/PublicLayout";
import { passwordProblem } from "./passwords";

/** The token from the link's fragment (#token=...), which browsers never send to a server. */
export function readResetToken(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return token && token.length >= 10 ? token : null;
}

function takeTokenFromUrl(): string | null {
  const token = readResetToken(window.location.hash);
  if (window.location.hash) {
    // Out of the address bar and history, so it cannot be copied, shared or bookmarked.
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  }
  return token;
}

export function ResetPasswordPage() {
  const [token] = useState(takeTokenFromUrl);
  const confirm = useConfirmPasswordReset();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [touched, setTouched] = useState(false);
  const problem = passwordProblem(password, repeat);

  if (!token) {
    return (
      <PublicLayout title="Reset your password">
        <p className="muted">
          This page needs the link from the reset email. Links work once, for 30
          minutes.
        </p>
        <Link to="/forgot-password">Ask for a new link</Link>
      </PublicLayout>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (problem || !token) return;
    confirm.mutate(
      { token, new_password: password },
      { onSuccess: () => navigate("/login?reset=done", { replace: true }) },
    );
  }

  return (
    <PublicLayout title="Choose a new password">
      <p className="muted">
        All your sign-ins and API keys stop working once you change it. Sign in
        again afterwards.
      </p>
      <form className="stack" onSubmit={submit}>
        <TextField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          hint="At least 12 characters."
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <TextField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          value={repeat}
          error={touched ? problem : null}
          onChange={(event) => setRepeat(event.target.value)}
        />
        <ErrorAlert error={confirm.error} />
        <Button type="submit" block busy={confirm.isPending}>
          Change password
        </Button>
      </form>
      {confirm.isError ? (
        <Link to="/forgot-password">Ask for a new link</Link>
      ) : null}
    </PublicLayout>
  );
}
