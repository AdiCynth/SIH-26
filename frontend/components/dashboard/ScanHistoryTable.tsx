"use client";

import Link from "next/link";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { TableRowSkeleton } from "@/components/ui/Skeleton";
import Alert from "@/components/ui/Alert";
import ScoreBadge from "@/components/ui/ScoreBadge";
import type { ScanSummary } from "@/lib/api";
import { formatDateTime, formatRelativeTime, repoDisplayName } from "@/lib/format";

type ScanHistoryTableProps = {
  scans: ScanSummary[];
  loading?: boolean;
  refreshError?: string | null;
};

const th =
  "px-4 py-2 text-left text-[11px] font-medium uppercase tracking-wide text-text-muted";
const thRight = `${th} text-right`;

export default function ScanHistoryTable({
  scans,
  loading = false,
  refreshError,
}: ScanHistoryTableProps) {
  return (
    <section aria-labelledby="scan-history-heading">
      <div className="mb-4 flex items-baseline justify-between">
        <div>
          <h2
            id="scan-history-heading"
            className="text-[17px] font-semibold tracking-tight text-text-primary"
          >
            Scan history
          </h2>
          <p className="mt-0.5 text-[13px] text-text-secondary">
            {scans.length > 0
              ? `${scans.length} analyses · auto-refreshes while active`
              : "Recent analyses will appear here."}
          </p>
        </div>
      </div>

      {refreshError && (
        <Alert variant="warning" className="mb-4">
          Lost contact with the server: {refreshError}. Retrying…
        </Alert>
      )}

      {loading ? (
        <div className="overflow-hidden border border-border bg-white">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className={th}>Repository</th>
                <th className={th}>Status</th>
                <th className={thRight}>Security</th>
                <th className={`${thRight} hidden sm:table-cell`}>Vibe Debt</th>
                <th className={`${thRight} hidden md:table-cell`}>Started</th>
                <th className={thRight}>Open</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 4 }).map((_, i) => (
                <TableRowSkeleton key={i} cols={6} />
              ))}
            </tbody>
          </table>
        </div>
      ) : scans.length === 0 ? (
        <EmptyState
          title="No analyses yet"
          description="Run your first repository analysis to identify vulnerabilities, security risks, license issues, and code quality concerns."
        />
      ) : (
        <>
          <div className="hidden overflow-hidden border border-border bg-white sm:block">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-surface-2">
                  <th scope="col" className={th}>Repository</th>
                  <th scope="col" className={th}>Status</th>
                  <th scope="col" className={thRight}>Security</th>
                  <th scope="col" className={`${thRight} hidden sm:table-cell`}>Vibe Debt</th>
                  <th scope="col" className={`${thRight} hidden md:table-cell`}>Started</th>
                  <th scope="col" className={thRight}>Open</th>
                </tr>
              </thead>
              <tbody>
                {scans.map((scan) => (
                  <tr
                    key={scan.id}
                    className="group border-b border-border-subtle last:border-0 transition-colors hover:bg-surface-2/60"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/scans/${scan.id}`}
                        className="inline-flex flex-col gap-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring rounded-sm"
                      >
                        <span className="font-mono text-[13px] font-medium text-text-primary group-hover:text-accent">
                          {repoDisplayName(scan.repo_key)}
                        </span>
                        <span className="font-mono text-[11px] text-text-muted">
                          scan #{scan.id} · {scan.mode}
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={scan.status} />
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <ScoreBadge label="Security" score={scan.security_score} />
                    </td>
                    <td className="hidden px-4 py-2.5 text-right sm:table-cell">
                      <ScoreBadge label="Vibe Debt" score={scan.vibe_debt_score} />
                    </td>
                    <td className="hidden px-4 py-2.5 text-right md:table-cell">
                      <time
                        dateTime={scan.created_at}
                        className="font-mono text-[12px] text-text-muted"
                        title={formatDateTime(scan.created_at)}
                      >
                        {formatRelativeTime(scan.created_at)}
                      </time>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <Link
                        href={`/scans/${scan.id}`}
                        className="text-[12px] font-medium text-accent hover:text-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring rounded-sm"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="flex flex-col divide-y divide-border-subtle border border-border bg-white sm:hidden">
            {scans.map((scan) => (
              <li key={scan.id}>
                <Link
                  href={`/scans/${scan.id}`}
                  className="flex flex-col gap-2 px-4 py-3 transition-colors hover:bg-surface-2/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono text-[13px] font-medium text-text-primary">
                      {repoDisplayName(scan.repo_key)}
                    </span>
                    <StatusBadge status={scan.status} />
                  </div>
                  <div className="flex items-center justify-between font-mono text-[12px] tabular-nums text-text-muted">
                    <div className="flex gap-3">
                      <span>Sec {scan.security_score ?? "—"}</span>
                      <span>Debt {scan.vibe_debt_score ?? "—"}</span>
                    </div>
                    <time dateTime={scan.created_at}>
                      {formatRelativeTime(scan.created_at)}
                    </time>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
