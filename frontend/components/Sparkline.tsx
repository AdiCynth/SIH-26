export default function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;

  const width = 160;
  const height = 40;
  const step = width / (points.length - 1);
  const path = points
    .map((value, i) => `${i === 0 ? "M" : "L"} ${i * step} ${height - (value / 100) * height}`)
    .join(" ");

  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
      <circle
        cx={width}
        cy={height - (points[points.length - 1] / 100) * height}
        r="3"
        fill="currentColor"
      />
    </svg>
  );
}
