import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router";

import { useSetupStatus, useSignUp } from "../api/queries";
import { useAuth } from "../auth/AuthProvider";
import { Alert, ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { TextField } from "../components/Field";
import { GoogleButton } from "../components/GoogleButton";
import { Spinner } from "../components/Spinner";
import { PublicLayout } from "../layout/PublicLayout";
import { passwordProblem } from "./passwords";

/** Create your own account (when the server allows sign-up), then go straight to onboarding. */
export function SignUpPage() {
  const { user, signIn } = useAuth();
  const setup = useSetupStatus();
  const signUp = useSignUp();
  // Signing in re-renders this page as signed in, so where that sends you must depend on
  // whether you have just signed up here (onboarding) or arrived already signed in (your shows).
  const justSignedUp = useRef(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (user)
    return (
      <Navigate to={justSignedUp.current ? "/welcome" : "/shows"} replace />
    );
  if (setup.isPending) {
    return (
      <PublicLayout title="Create your account" split>
        <Spinner label="Checking sign-up" />
      </PublicLayout>
    );
  }
  if (setup.data?.first_account_open) return <Navigate to="/setup" replace />;
  if (!setup.data?.signup_open) {
    return (
      <PublicLayout title="Create your account" split>
        <Alert tone="info">
          Sign-up is closed on this server. Ask your administrator to create an
          account for you.
        </Alert>
        <p style={{ fontSize: "var(--text-sm)" }}>
          <Link to="/login">Back to sign in</Link>
        </p>
      </PublicLayout>
    );
  }

  const problem = passwordProblem(password, confirm);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (problem) return;
    setError(null);
    try {
      await signUp.mutateAsync({ email: email.trim(), password });
      justSignedUp.current = true;
      await signIn(email.trim(), password); // the page then redirects, above
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <PublicLayout title="Create your account" split>
      {setup.data.google_sign_in ? (
        <>
          <GoogleButton label="Sign up with Google" />
          <p className="auth-or">or</p>
        </>
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
        <Button type="submit" block busy={signUp.isPending}>
          Create account
        </Button>
      </form>
      <p style={{ fontSize: "var(--text-sm)" }}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </PublicLayout>
  );
}
