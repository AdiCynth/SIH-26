export default function Sparkline({
  points,
  width = 220,
  height = 52,
}: {
  points: number[];
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;

  const padding = 4;
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;
  const step = innerW / (points.length - 1);

  const coords = points.map((value, i) => ({
    x: padding + i * step,
    y: padding + innerH - (value / 100) * innerH,
    value,
  }));

  const path = coords
    .map((c, i) => `${i === 0 ? "M" : "L"} ${c.x} ${c.y}`)
    .join(" ");

  const areaPath = `${path} L ${coords[coords.length - 1].x} ${height - padding} L ${coords[0].x} ${height - padding} Z`;

  const last = coords[coords.length - 1];
  const first = coords[0];
  const delta = last.value - first.value;

  return (
    <div className="flex items-end gap-5">
      <svg
        width={width}
        height={height}
        className="overflow-visible shrink-0"
        role="img"
        aria-label={`Security score trend from ${first.value} to ${last.value}`}
      >
        <defs>
          <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#spark-fill)" />
        <path
          d={path}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={last.x} cy={last.y} r="3" fill="var(--accent)" />
        {coords.slice(0, -1).map((c, i) => (
          <circle
            key={i}
            cx={c.x}
            cy={c.y}
            r="2"
            fill="white"
            stroke="var(--accent)"
            strokeWidth="1"
            opacity="0.7"
          />
        ))}
      </svg>
      <div className="flex flex-col gap-0.5 pb-1">
        <span className="font-mono text-[22px] font-semibold leading-none tabular-nums text-text-primary">
          {last.value}
        </span>
        <span
          className={`font-mono text-[11px] tabular-nums ${
            delta > 0
              ? "text-status-success"
              : delta < 0
                ? "text-status-error"
                : "text-text-muted"
          }`}
        >
          {delta > 0 ? "+" : ""}
          {delta !== 0 ? delta : "—"} vs first scan
        </span>
      </div>
    </div>
  );
}
