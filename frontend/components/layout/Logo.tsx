import Link from "next/link";

export default function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      href="/"
      className="group inline-flex items-center gap-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring rounded-sm"
      aria-label="VibeGuard home"
    >
      <span
        aria-hidden
        className="inline-flex size-6 items-center justify-center"
      >
        {/* Geometric brand mark: nested angle brackets forming a shield */}
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="square"
          strokeLinejoin="miter"
          className="text-accent"
        >
          <path d="M4 4 L12 2 L20 4 L20 12 L12 22 L4 12 Z" />
          <path d="M9 10 L11 12 L9 14" className="text-text-primary" />
          <path d="M13 10 L15 12 L13 14" className="text-text-primary" />
        </svg>
      </span>
      {!compact && (
        <span className="flex items-baseline gap-2 leading-none">
          <span className="text-[15px] font-semibold tracking-tight text-text-primary">
            VibeGuard
          </span>
          <span className="hidden text-[11px] font-normal text-text-muted sm:inline">
            Security analysis platform
          </span>
        </span>
      )}
    </Link>
  );
}
