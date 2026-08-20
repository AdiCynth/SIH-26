"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import FindingCard from "@/components/FindingCard";
import ScoreBadge from "@/components/ScoreBadge";
import Sparkline from "@/components/Sparkline";
import { ApiError, getScan, listScans, type ScanReport, type ScanSummary } from "@/lib/api";

export default function ScanPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const scanId = Number(id);
  const [scan, setScan] = useState<ScanReport | null>(null);
  const [history, setHistory] = useState<ScanSummary[]>([]);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const report = await getScan(scanId);
        if (!active) return;
        setScan(report);
        setRefreshError(null);
        if (report.status === "done" || report.status === "failed") {
          setHistory((await listScans(report.repo_key)).reverse());
          return;
        }
        timer = setTimeout(poll, 3000);
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setRefreshError(err instanceof Error ? err.message : "Could not load the scan");
        timer = setTimeout(poll, 3000);
      }
    }

    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [scanId, router]);

  if (!scan) {
    return (
      <main className="p-6 text-gray-500">
        {refreshError ? (
          <p className="text-red-600">
            Lost contact with the server: {refreshError}. Retrying…
          </p>
        ) : (
          "Loading…"
        )}
      </main>
    );
  }

  const trend = history
    .filter((s) => s.security_score !== null)
    .map((s) => s.security_score as number);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <Link href="/" className="text-sm underline">
        ← All scans
      </Link>

      {refreshError && (
        <p className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-600">
          Lost contact with the server: {refreshError}. Retrying…
        </p>
      )}

      <header className="mt-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{scan.repo_key}</h1>
          <p className="text-sm text-gray-500">
            {scan.status}
            {scan.mode === "diff" && " · diff only"} ·{" "}
            {new Date(scan.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex gap-2">
          <ScoreBadge label="Security" score={scan.security_score} />
          <ScoreBadge label="Vibe Debt" score={scan.vibe_debt_score} />
        </div>
      </header>

      {(scan.status === "pending" || scan.status === "running") && (
        <p className="mt-6 rounded border bg-gray-50 p-4 text-sm">
          Scanning… this page updates itself.
        </p>
      )}

      {scan.status === "failed" && (
        <p className="mt-6 rounded border border-red-300 bg-red-50 p-4 text-sm">
          Scan failed: {scan.error ?? "unknown error"}
        </p>
      )}

      {scan.status === "done" && scan.error && (
        <p className="mt-6 rounded border border-orange-400 bg-orange-50 p-4 text-sm text-orange-900">
          <span className="font-bold">Incomplete scan</span> — {scan.error}.
          Findings from that tool are missing from this report; absence of
          results does not mean absence of issues.
        </p>
      )}

      {scan.status === "done" && !scan.ai_available && (
        <p className="mt-4 rounded border border-gray-300 bg-gray-50 p-4 text-sm text-gray-600">
          AI explanations unavailable for this scan — findings below are raw
          scanner output.
        </p>
      )}

      {trend.length > 1 && (
        <section className="mt-8">
          <h2 className="mb-2 font-medium">Security score over time</h2>
          <div className="text-gray-800">
            <Sparkline points={trend} />
          </div>
          <p className="text-xs text-gray-500">
            {trend.length} scans of {scan.repo_key}
          </p>
        </section>
      )}

      {scan.status === "done" && (
        <section className="mt-8">
          <h2 className="mb-3 font-medium">
            {scan.findings.length} finding{scan.findings.length === 1 ? "" : "s"}
          </h2>
          {scan.findings.length === 0 ? (
            <p className="text-sm text-gray-500">Nothing flagged. Clean scan.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {scan.findings.map((finding) => (
                <FindingCard key={finding.id} finding={finding} />
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
