import type { Finding } from "@/lib/api";

const SEVERITY_TONE: Record<Finding["severity"], string> = {
  critical: "border-red-500 bg-red-50",
  high: "border-orange-500 bg-orange-50",
  medium: "border-amber-500 bg-amber-50",
  low: "border-sky-500 bg-sky-50",
  info: "border-gray-300 bg-gray-50",
};

export default function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className={`rounded border-l-4 p-4 ${SEVERITY_TONE[finding.severity]}`}>
      <div className="flex flex-wrap items-baseline gap-2 text-xs text-gray-600">
        <span className="font-semibold uppercase">{finding.severity}</span>
        <span>· {finding.category}</span>
        <span>· {finding.tool}</span>
        <span className="font-mono">
          {finding.file}
          {finding.line > 0 && `:${finding.line}`}
        </span>
      </div>
      <p className="mt-2 text-sm">{finding.message}</p>
      {finding.ai_explanation && (
        <p className="mt-3 text-sm">
          <span className="font-medium">Why it matters: </span>
          {finding.ai_explanation}
        </p>
      )}
      {finding.ai_fix && (
        <p className="mt-2 text-sm">
          <span className="font-medium">Suggested fix: </span>
          {finding.ai_fix}
        </p>
      )}
    </li>
  );
}
