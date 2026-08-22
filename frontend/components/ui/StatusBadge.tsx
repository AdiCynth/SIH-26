import type { ScanSummary } from "@/lib/api";

const STATUS_CONFIG: Record<
  ScanSummary["status"],
  { label: string; dot: string; text: string; pulse?: boolean }
> = {
  pending: {
    label: "Pending",
    dot: "bg-text-muted",
    text: "text-text-secondary",
  },
  running: {
    label: "Running",
    dot: "bg-status-info",
    text: "text-status-info",
    pulse: true,
  },
  done: {
    label: "Complete",
    dot: "bg-status-success",
    text: "text-status-success",
  },
  failed: {
    label: "Failed",
    dot: "bg-status-error",
    text: "text-status-error",
  },
};

export default function StatusBadge({
  status,
  className = "",
}: {
  status: ScanSummary["status"];
  showDot?: boolean;
  className?: string;
}) {
  const config = STATUS_CONFIG[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${config.text} ${className}`}
      role="status"
      aria-label={`Scan status: ${config.label}`}
    >
      <span
        className={`size-1.5 shrink-0 rounded-full ${config.dot} ${config.pulse ? "animate-pulse-dot" : ""}`}
        aria-hidden
      />
      {config.label}
    </span>
  );
}

export function StatusDot({ status }: { status: ScanSummary["status"] }) {
  const config = STATUS_CONFIG[status];
  return (
    <span
      className={`inline-block size-2 rounded-full ${config.dot} ${config.pulse ? "animate-pulse-dot" : ""}`}
      title={config.label}
      aria-label={config.label}
    />
  );
}
