type EmptyStateProps = {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
};

export default function EmptyState({
  title,
  description,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-start gap-2 border border-dashed border-border bg-surface-0 px-6 py-10 ${className}`}
      role="status"
    >
      <h3 className="text-[14px] font-semibold text-text-primary">{title}</h3>
      {description && (
        <p className="max-w-xl text-[13px] leading-relaxed text-text-secondary">
          {description}
        </p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function SecureEmptyState() {
  return (
    <div
      className="flex items-start gap-3 border border-status-success/25 bg-accent-subtle px-5 py-4"
      role="status"
    >
      <span aria-hidden className="mt-1 size-2 rounded-full bg-status-success" />
      <div>
        <h3 className="text-[13px] font-semibold text-status-success">
          No findings detected
        </h3>
        <p className="mt-0.5 text-[13px] text-text-secondary">
          This scan completed without flagged security issues, vibe debt, license
          conflicts, or drift.
        </p>
      </div>
    </div>
  );
}
