import Label from "./Label";

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
  monospace?: boolean;
};

export default function Input({
  label,
  hint,
  error,
  id,
  className = "",
  monospace = false,
  ...props
}: InputProps) {
  const inputId =
    id ?? (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

  return (
    <div className="flex flex-col gap-1.5">
      {label && <Label htmlFor={inputId}>{label}</Label>}
      <input
        id={inputId}
        className={`h-9 w-full rounded-[4px] border bg-white px-3 text-[13px] text-text-primary placeholder:text-text-muted transition-colors focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:cursor-not-allowed disabled:bg-surface-2 disabled:opacity-60 ${
          monospace ? "font-mono" : ""
        } ${error ? "border-status-error" : "border-border hover:border-border-strong"} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={
          error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined
        }
        {...props}
      />
      {hint && !error && (
        <p id={`${inputId}-hint`} className="text-[12px] text-text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={`${inputId}-error`}
          className="text-[12px] text-status-error"
          role="alert"
        >
          {error}
        </p>
      )}
    </div>
  );
}
