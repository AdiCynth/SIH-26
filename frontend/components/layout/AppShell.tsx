"use client";

import type { User } from "@/lib/api";
import Header from "./Header";

type AppShellProps = {
  email: string | null;
  user?: User | null;
  variant?: "dashboard" | "scan";
  actions?: React.ReactNode;
  children: React.ReactNode;
};

export default function AppShell({
  email,
  user,
  variant = "dashboard",
  actions,
  children,
}: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header email={email} user={user} variant={variant} actions={actions} />
      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-4 py-8 lg:px-8 lg:py-10">
          {children}
        </div>
      </main>
      <footer className="border-t border-border-subtle bg-header-bg">
        <div className="mx-auto flex h-9 max-w-7xl items-center justify-between px-4 lg:px-8">
          <span className="font-mono text-[11px] text-text-muted">
            vibeguard · security analysis platform
          </span>
          <span className="font-mono text-[11px] text-text-muted">
            v0.1
          </span>
        </div>
      </footer>
    </div>
  );
}
