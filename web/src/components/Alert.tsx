import type { ReactNode } from "react";

import { ApiError } from "../api/client";

type Tone = "error" | "success" | "info";

export function Alert({
  tone = "info",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  // Errors interrupt (role=alert); confirmations are announced politely.
  return (
    <div
      className={`alert alert-${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

/** The API writes messages in lower case ("wrong email or password"); show them as sentences. */
function sentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  const capital = trimmed[0].toUpperCase() + trimmed.slice(1);
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}

export function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429 && error.retryAfter) {
      return `${sentence(error.message)} Try again in about ${Math.ceil(error.retryAfter / 60)} minute(s).`;
    }
    return sentence(error.message);
  }
  if (error instanceof TypeError)
    return "The server could not be reached. Check your connection.";
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  return <Alert tone="error">{messageOf(error)}</Alert>;
}
