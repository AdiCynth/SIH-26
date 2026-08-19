export default function ScoreBadge({
  label,
  score,
}: {
  label: string;
  score: number | null;
}) {
  const tone =
    score === null ? "bg-gray-100 text-gray-500"
    : score >= 80 ? "bg-green-100 text-green-800"
    : score >= 50 ? "bg-amber-100 text-amber-800"
    : "bg-red-100 text-red-800";

  return (
    <span className={`inline-flex items-baseline gap-1 rounded px-2 py-1 text-sm ${tone}`}>
      <span className="font-medium">{label}</span>
      <span className="tabular-nums">{score ?? "—"}</span>
    </span>
  );
}
