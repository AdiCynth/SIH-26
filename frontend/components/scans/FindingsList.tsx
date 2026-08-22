"use client";

import { useMemo, useState } from "react";
import type { Finding } from "@/lib/api";
import { SEVERITY_ORDER } from "@/lib/severity";
import FindingRow from "./FindingRow";
import { SecureEmptyState } from "@/components/ui/EmptyState";

type FindingsListProps = {
  findings: Finding[];
  aiAvailable: boolean;
};

type SortKey = "severity" | "file" | "tool";

const selectClass =
  "h-8 rounded-[4px] border border-border bg-white px-2 text-[12px] text-text-secondary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent";

export default function FindingsList({ findings, aiAvailable }: FindingsListProps) {
  const [filter, setFilter] = useState<string>("all");
  const [sort, setSort] = useState<SortKey>("severity");

  const filtered = useMemo(() => {
    let list = [...findings];
    if (filter !== "all") list = list.filter((f) => f.severity === filter);
    list.sort((a, b) => {
      if (sort === "severity")
        return SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity);
      if (sort === "file") return a.file.localeCompare(b.file);
      return a.tool.localeCompare(b.tool);
    });
    return list;
  }, [findings, filter, sort]);

  if (findings.length === 0) return <SecureEmptyState />;

  return (
    <section aria-labelledby="findings-heading">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-baseline sm:justify-between">
        <div>
          <h2
            id="findings-heading"
            className="text-[17px] font-semibold tracking-tight text-text-primary"
          >
            Findings
            <span className="ml-2 font-mono text-[13px] font-normal text-text-muted tabular-nums">
              {findings.length}
            </span>
          </h2>
          {!aiAvailable && (
            <p className="mt-0.5 text-[12px] text-text-muted">
              AI explanations unavailable — raw scanner output shown.
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="severity-filter">
            Filter by severity
          </label>
          <select
            id="severity-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className={selectClass}
          >
            <option value="all">All severities</option>
            {SEVERITY_ORDER.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="findings-sort">
            Sort findings
          </label>
          <select
            id="findings-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className={selectClass}
          >
            <option value="severity">Sort: severity</option>
            <option value="file">Sort: file</option>
            <option value="tool">Sort: tool</option>
          </select>
        </div>
      </div>

      <div className="divide-y divide-border-subtle border border-border bg-white">
        {filtered.length === 0 ? (
          <p className="px-4 py-8 text-center text-[13px] text-text-muted">
            No findings match the selected filter.
          </p>
        ) : (
          filtered.map((finding) => (
            <FindingRow key={finding.id} finding={finding} />
          ))
        )}
      </div>
    </section>
  );
}
