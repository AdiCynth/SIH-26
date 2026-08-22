import Link from "next/link";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};

const variantClasses = {
  primary:
    "bg-accent text-white hover:bg-accent-hover border border-accent hover:border-accent-hover disabled:opacity-55",
  secondary:
    "bg-surface-0 text-text-primary hover:bg-surface-2 border border-border hover:border-border-strong",
  ghost:
    "bg-transparent text-text-secondary hover:text-text-primary hover:bg-surface-2 border border-transparent",
  danger:
    "bg-white text-status-error hover:bg-status-error/10 border border-status-error/40",
};

const sizeClasses = {
  sm: "h-8 px-3 text-[12px] gap-1.5",
  md: "h-9 px-4 text-[13px] gap-2",
  lg: "h-10 px-5 text-[13px] gap-2",
};

const base =
  "inline-flex items-center justify-center rounded-[4px] font-medium tracking-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed";

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={props.type ?? "button"}
      disabled={disabled || loading}
      className={`${base} ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...props}
    >
      {loading && (
        <span
          className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden
        />
      )}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "primary",
  size = "md",
  className = "",
  children,
}: {
  href: string;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`${base} ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {children}
    </Link>
  );
}
