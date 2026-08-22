const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Demo mode switch (enable with NEXT_PUBLIC_DEMO_MODE=true)
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

/* Demo integration point:
   If DEMO_MODE is enabled, selected API functions below will delegate
   to the demo implementations in `frontend/lib/demo/`. Keep all demo-only
   code confined to that folder so it can be removed easily before commit.
*/
import * as demo from "./demo";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  // If demo mode is enabled, route low-level requests to the demo layer.
  if (DEMO_MODE) {
    // demo.fetch mirrors the runtime behavior of the real backend fetch.
    return demo.fetch<T>(path, init);
  }

  const res = await fetch(`${BASE}${path}`, { credentials: "include", ...init });
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail;
    // FastAPI validation errors (422) send an array of objects, not a string;
    // passing that straight to Error renders as "[object Object]".
    const message = Array.isArray(detail)
      ? detail.map((d) => d?.msg).filter(Boolean).join("; ")
      : typeof detail === "string"
        ? detail
        : "";
    throw new ApiError(res.status, message || res.statusText);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export type User = { id: number; email: string };

export type ScanSummary = {
  id: number;
  repo_key: string;
  mode: "full" | "diff";
  status: "pending" | "running" | "done" | "failed";
  security_score: number | null;
  vibe_debt_score: number | null;
  created_at: string;
};

export type Finding = {
  id: number;
  tool: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: "security" | "vibe-debt" | "license" | "drift";
  file: string;
  line: number;
  message: string;
  license_id: string | null;
  ai_explanation: string | null;
  ai_fix: string | null;
};

export type ScanReport = ScanSummary & {
  ai_available: boolean;
  error: string | null;
  findings: Finding[];
};

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// Auth functions — delegate to demo implementations when DEMO_MODE is true.
export const signup = (email: string, password: string) =>
  DEMO_MODE ? demo.signup(email, password) : api<User>("/auth/signup", json({ email, password }));
export const login = (email: string, password: string) =>
  DEMO_MODE ? demo.login(email, password) : api<User>("/auth/login", json({ email, password }));
export const logout = () => (DEMO_MODE ? demo.logout() : api<void>("/auth/logout", { method: "POST" }));
export const me = () => (DEMO_MODE ? demo.me() : api<User>("/auth/me"));
export const githubLoginUrl = () => (DEMO_MODE ? demo.githubLoginUrl() : `${BASE}/auth/github/login`);

export const createScan = (form: FormData) =>
  DEMO_MODE ? demo.createScan(form) : api<{ id: number; status: string }>("/scans", { method: "POST", body: form });
export const listScans = (repoKey?: string) =>
  DEMO_MODE ? demo.listScans(repoKey) : api<ScanSummary[]>(`/scans${repoKey ? `?repo_key=${encodeURIComponent(repoKey)}` : ""}`);
export const getScan = (id: number) => (DEMO_MODE ? demo.getScan(id) : api<ScanReport>(`/scans/${id}`));
