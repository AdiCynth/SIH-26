import type { Finding } from "@/lib/api";
import { SEVERITY_LABEL, SEVERITY_ORDER, severityStyles } from "@/lib/severity";

type RiskDistributionProps = {
  findings: Finding[];
};

export default function RiskDistribution({ findings }: RiskDistributionProps) {
  const counts: Record<string, number> = {};
  for (const f of findings) counts[f.severity] = (counts[f.severity] ?? 0) + 1;
  const total = findings.length;

  return (
    <div className="border border-border bg-white">
      <div className="flex items-baseline justify-between border-b border-border-subtle px-4 py-2.5">
        <h3 className="text-[13px] font-semibold text-text-primary">
          Risk distribution
        </h3>
        <span className="font-mono text-[11px] text-text-muted tabular-nums">
          {total} findings
        </span>
      </div>
      <div className="flex flex-col divide-y divide-border-subtle">
        {SEVERITY_ORDER.map((sev) => {
          const count = counts[sev] ?? 0;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const styles = severityStyles(sev);
          return (
            <div
              key={sev}
              className="grid grid-cols-[80px_1fr_36px] items-center gap-3 px-4 py-2.5"
            >
              <div className="flex items-center gap-2">
                <span aria-hidden className={`size-1.5 rounded-full ${styles.dot}`} />
                <span className="text-[12px] font-medium text-text-secondary">
                  {SEVERITY_LABEL[sev]}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-[1px] bg-surface-3">
                <div
                  className={`h-full ${styles.bar}`}
                  style={{ width: `${pct}%` }}
                  aria-hidden
                />
              </div>
              <span className="text-right font-mono text-[13px] tabular-nums text-text-primary">
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
