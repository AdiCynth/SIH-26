import type { ScanSummary } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

type SystemStatusStripProps = {
  scans: ScanSummary[];
};

export default function SystemStatusStrip({ scans }: SystemStatusStripProps) {
  const active = scans.some((s) => s.status === "running" || s.status === "pending");
  const lastScan = scans[0];
  const repositories = new Set(scans.map((s) => s.repo_key)).size;
  const completed = scans.filter((s) => s.status === "done").length;

  const items: { label: string; value: React.ReactNode }[] = [
    {
      label: "Last analysis",
      value: lastScan ? (
        <span className="font-mono text-[13px] text-text-primary tabular-nums">
          {formatRelativeTime(lastScan.created_at)}
        </span>
      ) : (
        <span className="font-mono text-[13px] text-text-muted">—</span>
      ),
    },
    {
      label: "Repositories analyzed",
      value: (
        <span className="font-mono text-[13px] text-text-primary tabular-nums">
          {repositories}
        </span>
      ),
    },
    {
      label: "Analyses completed",
      value: (
        <span className="font-mono text-[13px] text-text-primary tabular-nums">
          {completed}
        </span>
      ),
    },
  ];

  return (
    <div className="flex flex-wrap items-stretch gap-x-8 gap-y-4 border-y border-border-subtle bg-white px-5 py-3.5">
      <div className="flex items-center gap-2 pr-6">
        <span
          aria-hidden
          className={`size-2 rounded-full ${active ? "bg-status-info animate-pulse-dot" : "bg-status-success"}`}
        />
        <span className="text-[13px] font-medium text-text-primary">
          {active ? "Analysis in progress" : "Analysis engine operational"}
        </span>
      </div>
      <div aria-hidden className="hidden h-6 w-px bg-border sm:block" />
      {items.map((item, idx) => (
        <div key={item.label} className="flex items-center gap-3">
          <div className="flex flex-col leading-tight">
            <span className="text-[11px] uppercase tracking-wide text-text-muted">
              {item.label}
            </span>
            <span>{item.value}</span>
          </div>
          {idx < items.length - 1 && (
            <span aria-hidden className="hidden h-6 w-px bg-border sm:block" />
          )}
        </div>
      ))}
    </div>
  );
}
