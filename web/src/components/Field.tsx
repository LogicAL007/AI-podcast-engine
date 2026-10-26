import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

interface FieldShell {
  label: string;
  hint?: ReactNode;
  error?: string | null;
}

function described(
  id: string,
  hint: ReactNode,
  error: string | null | undefined,
): string | undefined {
  const ids = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(
    Boolean,
  );
  return ids.length ? ids.join(" ") : undefined;
}

function Messages({
  id,
  hint,
  error,
}: {
  id: string;
  hint?: ReactNode;
  error?: string | null;
}) {
  return (
    <>
      {hint ? (
        <span id={`${id}-hint`} className="field-hint">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={`${id}-error`} className="field-error">
          {error}
        </span>
      ) : null}
    </>
  );
}

export function TextField({
  label,
  hint,
  error,
  ...input
}: FieldShell & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        className="input"
        aria-invalid={error ? true : undefined}
        aria-describedby={described(id, hint, error)}
        {...input}
      />
      <Messages id={id} hint={hint} error={error} />
    </div>
  );
}

export function TextArea({
  label,
  hint,
  error,
  ...input
}: FieldShell & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        className="textarea"
        aria-invalid={error ? true : undefined}
        aria-describedby={described(id, hint, error)}
        {...input}
      />
      <Messages id={id} hint={hint} error={error} />
    </div>
  );
}

export function SelectField({
  label,
  hint,
  error,
  options,
  ...select
}: FieldShell &
  SelectHTMLAttributes<HTMLSelectElement> & {
    options: { value: string; label: string }[];
  }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        className="select"
        aria-invalid={error ? true : undefined}
        aria-describedby={described(id, hint, error)}
        {...select}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <Messages id={id} hint={hint} error={error} />
    </div>
  );
}

export function CheckboxField({
  label,
  hint,
  ...input
}: {
  label: string;
  hint?: ReactNode;
} & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="check">
      <input
        id={id}
        type="checkbox"
        aria-describedby={hint ? `${id}-hint` : undefined}
        {...input}
      />
      <div className="field">
        <label htmlFor={id}>{label}</label>
        {hint ? (
          <span id={`${id}-hint`} className="field-hint">
            {hint}
          </span>
        ) : null}
      </div>
    </div>
  );
}
