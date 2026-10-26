import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useRequestPasswordReset } from "../api/queries";
import { Alert, ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { TextField } from "../components/Field";
import { PublicLayout } from "../layout/PublicLayout";

export function ForgotPasswordPage() {
  const request = useRequestPasswordReset();
  const [email, setEmail] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    request.mutate(email.trim());
  }

  return (
    <PublicLayout title="Reset your password">
      {request.isSuccess ? (
        // The API answers the same whether or not the account exists, and so does this page.
        <Alert tone="success">
          If an account exists for {email.trim()}, a reset link is on its way.
          It works once, for 30 minutes.
        </Alert>
      ) : (
        <form className="stack" onSubmit={submit}>
          <p className="muted">
            Enter your email and we will send you a link to choose a new
            password.
          </p>
          <TextField
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <ErrorAlert error={request.error} />
          <Button type="submit" block busy={request.isPending}>
            Send reset link
          </Button>
        </form>
      )}
      <p style={{ fontSize: "var(--text-sm)" }}>
        <Link to="/login">Back to sign in</Link>
      </p>
    </PublicLayout>
  );
}
