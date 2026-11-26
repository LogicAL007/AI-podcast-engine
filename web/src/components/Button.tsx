import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
  block?: boolean;
  children: ReactNode;
}

function classes(
  variant: Variant,
  block: boolean | undefined,
  extra?: string,
): string {
  return ["btn", `btn-${variant}`, block ? "btn-block" : "", extra ?? ""]
    .filter(Boolean)
    .join(" ");
}

export function Button({
  variant = "primary",
  busy = false,
  block,
  className,
  disabled,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={classes(variant, block, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <Spinner small /> : null}
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "primary",
  className,
  ...rest
}: LinkProps & { variant?: Variant }) {
  return <Link className={classes(variant, false, className)} {...rest} />;
}
