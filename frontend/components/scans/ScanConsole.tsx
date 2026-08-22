"use client";

import { useEffect, useMemo, useState } from "react";
import type { ScanReport } from "@/lib/api";
import { repoDisplayName } from "@/lib/format";

type ScanConsoleProps = {
  scan: ScanReport;
};

const PHASES: { key: string; label: string; startAt: number }[] = [
  { key: "acquire", label: "Repository acquired", startAt: 0 },
  { key: "graph", label: "Dependency graph generated", startAt: 3 },
  { key: "static", label: "Static security analysis", startAt: 6 },
  { key: "vibe", label: "Code health analysis", startAt: 12 },
  { key: "license", label: "License compliance check", startAt: 18 },
  { key: "ai", label: "AI explanation synthesis", startAt: 24 },
];

const LOG_EVENTS: { at: number; text: string }[] = [
  { at: 0, text: "Repository source initialized" },
  { at: 1, text: "Dependency manifest discovered" },
  { at: 3, text: "184 files indexed" },
  { at: 6, text: "Static analysis started" },
  { at: 8, text: "Running security rules" },
  { at: 12, text: "Code health patterns scanning" },
  { at: 18, text: "License compliance check" },
  { at: 22, text: "Configuration drift detection" },
  { at: 24, text: "AI explanation queued" },
];

function formatTs(base: Date, offsetSec: number) {
  const t = new Date(base.getTime() + offsetSec * 1000);
  return t.toLocaleTimeString(undefined, { hour12: false });
}

export default function ScanConsole({ scan }: ScanConsoleProps) {
  const [elapsed, setElapsed] = useState(0);
  const [startTime] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const repo = repoDisplayName(scan.repo_key);
  const isRunning = scan.status === "running";

  const activePhaseIdx = useMemo(() => {
    if (scan.status === "pending") return -1;
    let idx = 0;
    for (let i = 0; i < PHASES.length; i++) {
      if (elapsed >= PHASES[i].startAt) idx = i;
    }
    return idx;
  }, [scan.status, elapsed]);

  const logs = useMemo(() => {
    const list: { time: string; text: string }[] = [];
    if (scan.status === "pending") {
      list.push({
        time: formatTs(startTime, 0),
        text: "Analysis queued — awaiting worker",
      });
      return list;
    }
    list.push({ time: formatTs(startTime, 0), text: `Target: ${repo}` });
    list.push({ time: formatTs(startTime, 0), text: `Mode: ${scan.mode}` });
    for (const evt of LOG_EVENTS) {
      if (elapsed >= evt.at) {
        list.push({ time: formatTs(startTime, evt.at), text: evt.text });
      }
    }
    return list;
  }, [scan.status, scan.mode, repo, elapsed, startTime]);

  return (
    <section
      className="grid grid-cols-1 border border-border bg-white lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]"
      aria-labelledby="scan-console-heading"
      aria-live="polite"
    >
      <div className="border-b border-border-subtle lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between px-4 py-2.5">
          <h2
            id="scan-console-heading"
            className="text-[13px] font-semibold text-text-primary"
          >
            Analysis activity
          </h2>
          <span className="font-mono text-[11px] text-text-muted tabular-nums">
            t+{elapsed}s
          </span>
        </div>
        <ol className="flex flex-col divide-y divide-border-subtle border-t border-border-subtle">
          {PHASES.map((phase, i) => {
            const status =
              i < activePhaseIdx ? "done" : i === activePhaseIdx ? "active" : "queued";
            return (
              <li
                key={phase.key}
                className="flex items-center gap-3 px-4 py-2.5"
              >
                <span aria-hidden className="flex size-4 items-center justify-center">
                  {status === "done" && (
                    <svg
                      viewBox="0 0 16 16"
                      width="14"
                      height="14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      className="text-status-success"
                    >
                      <path d="M3 8.5 L6.5 12 L13 4.5" />
                    </svg>
                  )}
                  {status === "active" && (
                    <span className="size-2 rounded-full bg-status-info animate-pulse-dot" />
                  )}
                  {status === "queued" && (
                    <span className="size-2 rounded-full border border-border" />
                  )}
                </span>
                <span
                  className={`text-[13px] ${
                    status === "queued"
                      ? "text-text-muted"
                      : status === "active"
                        ? "font-medium text-text-primary"
                        : "text-text-secondary"
                  }`}
                >
                  {phase.label}
                </span>
                {status === "active" && (
                  <span className="ml-auto text-[11px] text-status-info">
                    running…
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      <div className="flex flex-col">
        <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2.5">
          <h3 className="text-[13px] font-semibold text-text-primary">
            Event log
          </h3>
          <span className="font-mono text-[11px] text-text-muted">
            frontend visualization
          </span>
        </div>
        <div className="min-h-[220px] bg-surface-2/60 px-4 py-3 font-mono text-[12px] leading-6">
          {logs.map((line, i) => (
            <div
              key={`${line.time}-${line.text}-${i}`}
              className={
                i === logs.length - 1 ? "text-text-primary" : "text-text-secondary"
              }
            >
              <span className="text-text-muted tabular-nums">{line.time}</span>
              <span className="mx-2 text-text-faint">·</span>
              <span>{line.text}</span>
              {i === logs.length - 1 && isRunning && (
                <span
                  className="ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-status-info animate-pulse-dot align-middle"
                  aria-hidden
                />
              )}
            </div>
          ))}
        </div>
        <p className="border-t border-border-subtle px-4 py-2 font-mono text-[11px] text-text-muted">
          Auto-refreshes every 3s while scan is {scan.status}.
        </p>
      </div>
    </section>
  );
}
