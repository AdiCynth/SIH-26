"use client";

import { useState } from "react";
import type { Finding } from "@/lib/api";
import { SEVERITY_LABEL, severityStyles } from "@/lib/severity";

type FindingRowProps = {
  finding: Finding;
  defaultExpanded?: boolean;
};

export default function FindingRow({
  finding,
  defaultExpanded = false,
}: FindingRowProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);
  const styles = severityStyles(finding.severity);
  const hasDetails =
    !!finding.ai_explanation || !!finding.ai_fix || !!finding.license_id;

  async function copyFix() {
    if (!finding.ai_fix) return;
    try {
      await navigator.clipboard.writeText(finding.ai_fix);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard denied; silent
    }
  }

  return (
    <article className={`group border-l-2 bg-white ${styles.border}`}>
      <button
        type="button"
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`flex w-full items-start gap-4 px-4 py-3 text-left transition-colors hover:bg-surface-2/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring ${
          hasDetails ? "cursor-pointer" : "cursor-default"
        }`}
        aria-expanded={hasDetails ? expanded : undefined}
      >
        <span
          aria-hidden
          className={`mt-1 flex size-4 shrink-0 items-center justify-center`}
        >
          <span className={`size-2 rounded-full ${styles.dot}`} />
        </span>

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span
              className={`text-[11px] font-semibold uppercase tracking-wide ${styles.text}`}
            >
              {SEVERITY_LABEL[finding.severity]}
            </span>
            <span className="text-[13px] font-medium text-text-primary">
              {finding.message}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[12px] text-text-muted">
            {finding.file && (
              <span className="text-text-secondary">
                {finding.file}
                {finding.line > 0 && (
                  <span className="text-text-muted">:{finding.line}</span>
                )}
              </span>
            )}
            {finding.file && <span aria-hidden className="text-text-faint">·</span>}
            <span className="uppercase tracking-wide">{finding.tool}</span>
            <span aria-hidden className="text-text-faint">·</span>
            <span>{finding.category}</span>
            {finding.license_id && (
              <>
                <span aria-hidden className="text-text-faint">·</span>
                <span>{finding.license_id}</span>
              </>
            )}
          </div>
        </div>

        {hasDetails && (
          <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-[12px] text-text-secondary">
            {expanded ? "Collapse" : "Expand"}
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              className={`transition-transform ${expanded ? "rotate-180" : ""}`}
              aria-hidden
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        )}
      </button>

      {expanded && hasDetails && (
        <div className="border-t border-border-subtle bg-surface-2/40 px-4 py-4">
          <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
            {finding.ai_explanation && (
              <>
                <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                  Why this matters
                </span>
                <p className="text-[13px] leading-relaxed text-text-secondary">
                  {finding.ai_explanation}
                </p>
              </>
            )}
            {finding.ai_fix && (
              <>
                <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                  Recommended fix
                </span>
                <div>
                  <div className="flex items-center justify-between border border-border bg-white">
                    <span className="border-r border-border-subtle px-3 py-1.5 font-mono text-[11px] text-text-muted">
                      suggested-fix
                    </span>
                    <button
                      type="button"
                      onClick={copyFix}
                      className="px-3 py-1.5 text-[11px] font-medium text-text-secondary hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                    >
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                  <pre className="overflow-x-auto border-x border-b border-border bg-white px-3 py-3 font-mono text-[12px] leading-relaxed text-text-primary whitespace-pre-wrap">
                    {finding.ai_fix}
                  </pre>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
