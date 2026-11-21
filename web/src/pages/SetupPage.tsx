import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";

import { useRegisterFirstAccount, useSetupStatus } from "../api/queries";
import { useAuth } from "../auth/AuthProvider";
import { ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { TextField } from "../components/Field";
import { Spinner } from "../components/Spinner";
import { PublicLayout } from "../layout/PublicLayout";
import { passwordProblem } from "./passwords";

/** First run: create the admin account, then sign in with it. */
export function SetupPage() {
  const setup = useSetupStatus();
  const register = useRegisterFirstAccount();
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (setup.isPending) {
    return (
      <PublicLayout title="Set up Oasis">
        <Spinner label="Checking setup" />
      </PublicLayout>
    );
  }
  if (!setup.data?.first_account_open && !register.isSuccess)
    return <Navigate to="/login" replace />;

  const problem = passwordProblem(password, confirm);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (problem) return;
    setError(null);
    try {
      await register.mutateAsync({ email: email.trim(), password });
      await signIn(email.trim(), password);
      navigate("/welcome", { replace: true });
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <PublicLayout title="Set up Oasis">
      <p className="muted">
        Create the first account. It becomes the administrator, and takes over
        any shows made before sign-in existed.
      </p>
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
          autoComplete="new-password"
          required
          minLength={12}
          hint="At least 12 characters. A passphrase of a few words is best."
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <TextField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          error={touched ? problem : null}
          onChange={(event) => setConfirm(event.target.value)}
        />
        <ErrorAlert error={error} />
        <Button type="submit" block busy={register.isPending}>
          Create account
        </Button>
      </form>
    </PublicLayout>
  );
}
