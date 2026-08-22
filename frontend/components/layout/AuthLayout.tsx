"use client";

import Link from "next/link";
import Logo from "@/components/layout/Logo";

export default function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="border-b border-border bg-header-bg">
        <div className="mx-auto flex h-12 max-w-6xl items-center px-4 lg:px-8">
          <Logo />
        </div>
      </header>

      <main className="relative flex flex-1 flex-col items-center justify-center px-6 py-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 surface-grid opacity-40"
        />
        <div className="relative w-full max-w-sm animate-fade-in">
          <div className="mb-8 flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
              VibeGuard
            </span>
            <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">
              {title}
            </h1>
            {subtitle && (
              <p className="text-[13px] text-text-secondary">{subtitle}</p>
            )}
          </div>

          <div className="border border-border bg-white p-6">{children}</div>

          {footer && (
            <p className="mt-4 text-center text-[13px] text-text-secondary">
              {footer}
            </p>
          )}

          <p className="mt-8 text-center font-mono text-[11px] text-text-muted">
            security analysis for modern codebases
          </p>
        </div>
      </main>
    </div>
  );
}

export function AuthDivider() {
  return (
    <div className="relative my-5 flex items-center">
      <div className="flex-1 border-t border-border-subtle" />
      <span className="px-3 text-[11px] font-medium uppercase tracking-wide text-text-muted">
        or
      </span>
      <div className="flex-1 border-t border-border-subtle" />
    </div>
  );
}

export function AuthLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="font-medium text-accent hover:text-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring rounded-sm"
    >
      {children}
    </Link>
  );
}
