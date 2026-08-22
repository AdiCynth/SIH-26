// Demo / Mock API layer for frontend local development.
// This entire folder is isolated for demo mode and can be removed before commit.
// Enable with NEXT_PUBLIC_DEMO_MODE=true

import type { User, ScanSummary, ScanReport, Finding } from "../api";

// Small helper to simulate latency
const wait = (ms = 150) => new Promise((r) => setTimeout(r, ms));

let nextScanId = 100;

const demoUser: User = { id: 1, email: "demo@local" };

// Seeded demo data
const demoFindings: Finding[] = [
  {
    id: 1,
    tool: "bandit",
    severity: "high",
    category: "security",
    file: "src/auth.ts",
    line: 42,
    message: "Use of weak cryptographic primitive",
    license_id: null,
    ai_explanation: "This function uses MD5 which is considered insecure for cryptographic use.",
    ai_fix: "Replace MD5 usage with SHA-256 or a modern KDF like Argon2.",
  },
  {
    id: 2,
    tool: "eslint",
    severity: "medium",
    category: "vibe-debt",
    file: "src/components/Button.tsx",
    line: 12,
    message: "Prefer using semantic HTML for accessibility",
    license_id: null,
    ai_explanation: "Using non-semantic elements reduces accessibility for assistive tech.",
    ai_fix: "Use a `<button>` element instead of a clickable `<div>`.",
  },
  {
    id: 3,
    tool: "license-checker",
    severity: "info",
    category: "license",
    file: "",
    line: 0,
    message: "Found dependency with unknown license: some-legacy-lib",
    license_id: "UNKNOWN",
    ai_explanation: null,
    ai_fix: null,
  },
  {
    id: 4,
    tool: "drift-detector",
    severity: "low",
    category: "drift",
    file: "Dockerfile",
    line: 3,
    message: "Base image tag differs from declared CI image",
    license_id: null,
    ai_explanation: "CI uses node:18-alpine but Dockerfile pins node:16.",
    ai_fix: "Update Dockerfile to match CI base image version.",
  },
];

// A small in-memory scans list to drive the UI
const scans: ScanSummary[] = [
  {
    id: 1,
    repo_key: "github.com/demo/awesome-app",
    mode: "full",
    status: "done",
    security_score: 78,
    vibe_debt_score: 62,
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 3).toISOString(),
  },
  {
    id: 2,
    repo_key: "github.com/demo/another-repo",
    mode: "diff",
    status: "running",
    security_score: null,
    vibe_debt_score: null,
    created_at: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
  },
  {
    id: 3,
    repo_key: "github.com/demo/new-repo",
    mode: "full",
    status: "pending",
    security_score: null,
    vibe_debt_score: null,
    created_at: new Date().toISOString(),
  },
];

// Map of scan id -> report findings and metadata
const reports: Record<number, ScanReport> = {
  1: {
    ...scans[0],
    ai_available: true,
    error: null,
    findings: demoFindings,
  },
};

// Exported functions used by frontend api.ts
export async function fetch<T>(_path: string, _init: RequestInit = {}): Promise<T> {
  // Low-level demo fetch: we route higher-level calls to their functions below,
  // so this only needs to satisfy any direct low-level usage.
  await wait();
  // reference _init to avoid unused-var lint
  void _init;
  // Naive default
  return Promise.reject(new Error("demo: unsupported low-level fetch path"));
}

export async function signup(email: string, _password?: string): Promise<User> {
  await wait();
  // In demo mode we accept any signup and return the demo user.
  return { ...demoUser, email };
}

export async function login(email: string, _password?: string): Promise<User> {
  await wait();
  return { ...demoUser, email };
}

export async function logout(): Promise<void> {
  await wait();
  return;
}

export async function me(): Promise<User> {
  await wait();
  return demoUser;
}

export function githubLoginUrl() {
  // Keep user in demo; link can no-op or point to project root.
  return "#";
}

export async function createScan(form: FormData): Promise<{ id: number; status: string }> {
  await wait(300);
  const id = nextScanId++;
  const repo_url = form.get("repo_url")?.toString() ?? `github.com/demo/new-${id}`;
  const repo_key = repo_url.replace(/^https?:\/\//, "");
  const mode = form.get("base_ref") && form.get("head_ref") ? "diff" : "full";
  const newScan: ScanSummary = {
    id,
    repo_key,
    mode: mode as "full" | "diff",
    status: "pending",
    security_score: null,
    vibe_debt_score: null,
    created_at: new Date().toISOString(),
  };
  scans.unshift(newScan);

  // schedule progress: pending -> running -> done
  setTimeout(() => {
    const s = scans.find((x) => x.id === id);
    if (!s) return;
    s.status = "running";
    // after another delay, mark done and create a report with findings
    setTimeout(() => {
      s.status = "done";
      s.security_score = 70 + (id % 10);
      s.vibe_debt_score = 50 + (id % 10);
      reports[id] = {
        ...s,
        ai_available: true,
        error: null,
        findings: demoFindings.map((f) => ({ ...f, id: f.id + id * 10 })),
      };
    }, 1500);
  }, 800);

  return { id, status: newScan.status };
}

export async function listScans(repoKey?: string): Promise<ScanSummary[]> {
  await wait();
  if (!repoKey) return scans.slice();
  return scans.filter((s) => s.repo_key.includes(repoKey));
}

export async function getScan(id: number): Promise<ScanReport> {
  // If the report exists, return it. Otherwise, construct a progressive report.
  await wait();
  const s = scans.find((x) => x.id === id);
  if (!s) {
    throw new Error("Scan not found");
  }
  if (reports[id]) return reports[id];

  // For pending/running scans return a minimal report that reflects current status.
  const partial: ScanReport = {
    ...s,
    ai_available: false,
    error: null,
    findings: s.status === "done" ? demoFindings.map((f) => ({ ...f, id: f.id + id * 10 })) : [],
  };
  return partial;
}

const exported = {
  fetch,
  signup,
  login,
  logout,
  me,
  githubLoginUrl,
  createScan,
  listScans,
  getScan,
};

export default exported;

