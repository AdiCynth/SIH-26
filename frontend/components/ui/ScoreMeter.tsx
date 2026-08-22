import { scoreTone, vibeDebtTone } from "@/lib/severity";

type ScoreMeterProps = {
  label: string;
  score: number | null;
  variant?: "security" | "vibe-debt";
  segments?: number;
  className?: string;
};

export default function ScoreMeter({
  label,
  score,
  variant = "security",
  segments = 20,
  className = "",
}: ScoreMeterProps) {
  const tone = variant === "vibe-debt" ? vibeDebtTone(score) : scoreTone(score);
  const filled =
    score === null
      ? 0
      : Math.max(0, Math.min(segments, Math.round((score / 100) * segments)));

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex items-baseline gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
          {label}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span
          className={`font-mono text-[26px] font-semibold leading-none tabular-nums ${tone.value}`}
        >
          {score ?? "—"}
        </span>
        <span className="font-mono text-[12px] text-text-muted">/ 100</span>
      </div>
      <div
        className="flex gap-[3px]"
        role="progressbar"
        aria-valuenow={score ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        {Array.from({ length: segments }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-[1px] ${
              i < filled ? tone.bar : "bg-surface-3"
            }`}
            aria-hidden
          />
        ))}
      </div>
      <span className={`text-[12px] font-medium ${tone.value}`}>
        {tone.qualifier}
      </span>
    </div>
  );
}
