import { scoreTone } from "@/lib/severity";

type ScoreBadgeProps = {
  label: string;
  score: number | null;
  className?: string;
};

/** Compact numeric score used in tables. */
export default function ScoreBadge({
  label,
  score,
  className = "",
}: ScoreBadgeProps) {
  const tone = scoreTone(score);

  return (
    <span
      className={`inline-flex items-baseline gap-1 ${className}`}
      aria-label={`${label}: ${score ?? "not available"}`}
    >
      <span className={`font-mono text-[13px] font-semibold tabular-nums ${tone.value}`}>
        {score ?? "—"}
      </span>
    </span>
  );
}
