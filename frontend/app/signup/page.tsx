"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { githubLoginUrl, signup } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signup(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-2xl font-semibold">Create a VibeGuard account</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <input
          type="email" required placeholder="you@example.com" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        <input
          type="password" required minLength={8} placeholder="Password (8+ characters)"
          value={password} onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="rounded bg-black px-3 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <a href={githubLoginUrl()} className="rounded border px-3 py-2 text-center">
        Continue with GitHub
      </a>
      <p className="text-sm text-gray-600">
        Already registered? <Link href="/login" className="underline">Sign in</Link>
      </p>
    </main>
  );
}
