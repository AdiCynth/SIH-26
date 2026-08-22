type BadgeProps = {
  children: React.ReactNode;
  variant?: "default" | "outline" | "muted" | "accent";
  className?: string;
};

const variants = {
  default: "bg-surface-2 text-text-secondary border-border",
  outline: "bg-transparent text-text-secondary border-border",
  muted: "bg-surface-2 text-text-muted border-border-subtle",
  accent: "bg-accent-subtle text-accent border-accent/25",
};

export default function Badge({
  children,
  variant = "default",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-[3px] px-1.5 py-0.5 text-[11px] font-medium border ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
