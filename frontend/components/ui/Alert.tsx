type AlertProps = {
  variant?: "error" | "warning" | "info" | "success";
  title?: string;
  children: React.ReactNode;
  className?: string;
};

const variants = {
  error: {
    border: "border-status-error/35",
    bg: "bg-status-error/6",
    dot: "bg-status-error",
    text: "text-status-error",
  },
  warning: {
    border: "border-status-warning/40",
    bg: "bg-status-warning/8",
    dot: "bg-status-warning",
    text: "text-status-warning",
  },
  info: {
    border: "border-status-info/35",
    bg: "bg-status-info/6",
    dot: "bg-status-info",
    text: "text-status-info",
  },
  success: {
    border: "border-status-success/35",
    bg: "bg-accent-subtle",
    dot: "bg-status-success",
    text: "text-status-success",
  },
};

export default function Alert({
  variant = "info",
  title,
  children,
  className = "",
}: AlertProps) {
  const v = variants[variant];
  return (
    <div
      className={`flex gap-3 rounded-[6px] border-l-2 ${v.border.replace("border-", "border-l-")} border-y border-r border-border-subtle ${v.bg} px-4 py-3 text-[13px] ${className}`}
      role="alert"
    >
      <span aria-hidden className={`mt-1.5 size-1.5 shrink-0 rounded-full ${v.dot}`} />
      <div className="min-w-0 flex-1">
        {title && (
          <p className={`mb-0.5 text-[13px] font-semibold ${v.text}`}>{title}</p>
        )}
        <div className="text-text-secondary leading-relaxed [&_strong]:text-text-primary">
          {children}
        </div>
      </div>
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-start gap-2 rounded-[6px] border border-status-error/30 bg-status-error/6 px-4 py-4"
      role="alert"
    >
      <h3 className="text-[13px] font-semibold text-status-error">{title}</h3>
      <p className="max-w-2xl text-[13px] text-text-secondary">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 text-[13px] font-medium text-accent hover:text-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          Try again →
        </button>
      )}
    </div>
  );
}
