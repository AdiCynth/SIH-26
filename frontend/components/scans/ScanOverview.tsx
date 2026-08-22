import Link from "next/link";
import Badge from "@/components/ui/Badge";
import ScoreMeter from "@/components/ui/ScoreMeter";
import StatusBadge from "@/components/ui/StatusBadge";
import Sparkline from "@/components/Sparkline";
import type { ScanReport } from "@/lib/api";
import { formatDateTime, repoDisplayName } from "@/lib/format";

type ScanOverviewProps = {
  scan: ScanReport;
  trend?: number[];
};

export default function ScanOverview({ scan, trend }: ScanOverviewProps) {
  const findingCount = scan.findings.length;

  return (
    <section className="flex flex-col gap-6" aria-labelledby="scan-overview">
      {/* Breadcrumb */}
      <nav
        aria-label="Breadcrumb"
        className="font-mono text-[12px] text-text-muted"
      >
        <Link href="/" className="hover:text-text-primary">
          Dashboard
        </Link>
        <span className="mx-1.5 text-text-faint">/</span>
        <span className="text-text-secondary">{repoDisplayName(scan.repo_key)}</span>
      </nav>

      {/* Title block */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1
            id="scan-overview"
            className="text-[22px] font-semibold tracking-tight text-text-primary sm:text-[24px]"
          >
            {repoDisplayName(scan.repo_key)}
          </h1>
          {scan.mode === "diff" && <Badge variant="outline">Diff scan</Badge>}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[12px] text-text-muted">
          <StatusBadge status={scan.status} />
          <span aria-hidden className="text-text-faint">·</span>
          <span>
            <span className="text-text-faint">scan </span>#{scan.id}
          </span>
          <span aria-hidden className="text-text-faint">·</span>
          <time dateTime={scan.created_at}>{formatDateTime(scan.created_at)}</time>
          {scan.status === "done" && (
            <>
              <span aria-hidden className="text-text-faint">·</span>
              <span className="tabular-nums">
                {findingCount} findings
              </span>
            </>
          )}
        </div>
      </div>

      {/* Analysis summary strip */}
      <div className="grid grid-cols-1 gap-8 border-y border-border-subtle bg-white px-5 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <ScoreMeter label="Security score" score={scan.security_score} variant="security" />
        <ScoreMeter label="Vibe debt" score={scan.vibe_debt_score} variant="vibe-debt" />
        <SummaryStat
          label="Findings"
          value={scan.status === "done" ? String(findingCount) : "—"}
          hint={
            scan.status === "done"
              ? `${scan.findings.filter((f) => f.severity === "critical").length} critical`
              : scan.status === "running"
                ? "Awaiting completion"
                : ""
          }
        />
        <SummaryStat
          label="Analysis mode"
          value={scan.mode === "diff" ? "Diff" : "Full"}
          hint={scan.ai_available ? "AI explanations available" : "Raw scanner output"}
        />
      </div>

      {trend && trend.length > 1 && (
        <div className="border border-border bg-white">
          <div className="flex items-baseline justify-between border-b border-border-subtle px-4 py-2.5">
            <h2 className="text-[13px] font-semibold text-text-primary">
              Security score trend
            </h2>
            <span className="font-mono text-[11px] text-text-muted">
              {trend.length} scans
            </span>
          </div>
          <div className="px-4 py-4">
            <Sparkline points={trend} />
          </div>
        </div>
      )}
    </section>
  );
}

function SummaryStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
        {label}
      </span>
      <span className="font-mono text-[26px] font-semibold leading-none tabular-nums text-text-primary">
        {value}
      </span>
      {hint && (
        <span className="text-[12px] text-text-secondary">{hint}</span>
      )}
    </div>
  );
}
