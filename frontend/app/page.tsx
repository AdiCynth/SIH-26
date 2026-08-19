"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ScoreBadge from "@/components/ScoreBadge";
import { createScan, listScans, logout, me, type ScanSummary } from "@/lib/api";

export default function Dashboard() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [repoUrl, setRepoUrl] = useState("");
  const [zip, setZip] = useState<File | null>(null);
  const [baseRef, setBaseRef] = useState("");
  const [headRef, setHeadRef] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setScans(await listScans());
  }, []);

  useEffect(() => {
    me()
      .then((user) => setEmail(user.email))
      .then(refresh)
      .catch(() => router.push("/login"));
  }, [refresh, router]);

  // Past scans include pending/running ones; poll while any are unfinished.
  useEffect(() => {
    if (!scans.some((s) => s.status === "pending" || s.status === "running")) return;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [scans, refresh]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    if (repoUrl) form.append("repo_url", repoUrl);
    if (zip) form.append("zip_file", zip);
    if (baseRef && headRef) {
      form.append("base_ref", baseRef);
      form.append("head_ref", headRef);
    }
    try {
      const created = await createScan(form);
      router.push(`/scans/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the scan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">VibeGuard</h1>
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <span>{email}</span>
          <button
            onClick={() => logout().then(() => router.push("/login"))}
            className="underline"
          >
            Sign out
          </button>
        </div>
      </header>

      <form onSubmit={submit} className="mb-10 flex flex-col gap-3 rounded border p-4">
        <h2 className="font-medium">Scan a repository</h2>
        <input
          type="url" placeholder="https://github.com/owner/repo" value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        <div className="text-center text-sm text-gray-500">or upload a zip</div>
        <input
          type="file" accept=".zip"
          onChange={(e) => setZip(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-600">
            Scan only a diff (optional)
          </summary>
          <div className="mt-2 flex gap-2">
            <input
              placeholder="base ref (e.g. main)" value={baseRef}
              onChange={(e) => setBaseRef(e.target.value)}
              className="flex-1 rounded border border-gray-300 px-3 py-2"
            />
            <input
              placeholder="head ref (e.g. my-branch)" value={headRef}
              onChange={(e) => setHeadRef(e.target.value)}
              className="flex-1 rounded border border-gray-300 px-3 py-2"
            />
          </div>
        </details>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy || (!repoUrl && !zip)}
          className="self-start rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Starting…" : "Start scan"}
        </button>
      </form>

      <h2 className="mb-3 font-medium">Past scans</h2>
      {scans.length === 0 ? (
        <p className="text-sm text-gray-500">Nothing scanned yet.</p>
      ) : (
        <ul className="divide-y rounded border">
          {scans.map((scan) => (
            <li key={scan.id}>
              <Link
                href={`/scans/${scan.id}`}
                className="flex items-center justify-between gap-3 p-3 hover:bg-gray-50"
              >
                <div>
                  <div className="font-medium">{scan.repo_key}</div>
                  <div className="text-xs text-gray-500">
                    {scan.status}
                    {scan.mode === "diff" && " · diff"} ·{" "}
                    {new Date(scan.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  <ScoreBadge label="Security" score={scan.security_score} />
                  <ScoreBadge label="Vibe Debt" score={scan.vibe_debt_score} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
