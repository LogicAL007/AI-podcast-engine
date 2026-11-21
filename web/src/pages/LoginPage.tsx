import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { useSetupStatus } from "../api/queries";
import { useAuth } from "../auth/AuthProvider";
import { safeNext } from "../auth/RequireAuth";
import { Alert, ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { TextField } from "../components/Field";
import { GOOGLE_PROBLEMS, GoogleButton } from "../components/GoogleButton";
import { PublicLayout } from "../layout/PublicLayout";

export function LoginPage() {
  const { user, signIn } = useAuth();
  const setup = useSetupStatus();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const googleProblem = GOOGLE_PROBLEMS[params.get("google") ?? ""];

  if (user) return <Navigate to={next} replace />;
  if (setup.data?.first_account_open) return <Navigate to="/setup" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      navigate(next, { replace: true });
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PublicLayout title="Sign in to Oasis" split>
      {googleProblem ? <Alert tone="error">{googleProblem}</Alert> : null}
      {setup.data?.google_sign_in ? (
        <>
          <GoogleButton label="Sign in with Google" next={next} />
          <p className="auth-or">or</p>
        </>
      ) : null}
      {params.get("reset") === "done" ? (
        <Alert tone="success">
          Your password was changed. Sign in with the new one.
        </Alert>
      ) : null}
      <form className="stack" onSubmit={submit}>
        <TextField
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <ErrorAlert error={error} />
        <Button type="submit" block busy={busy}>
          Sign in
        </Button>
      </form>
      <p style={{ fontSize: "var(--text-sm)" }}>
        <Link to="/forgot-password">Forgot your password?</Link>
      </p>
      {setup.data?.signup_open ? (
        <p className="signup-prompt">
          New here? <Link to="/signup">Create an account</Link>
        </p>
      ) : null}
    </PublicLayout>
  );
}
