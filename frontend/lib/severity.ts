import type { Finding } from "@/lib/api";

export type Severity = Finding["severity"];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

export const SEVERITY_ORDER: Severity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];

export function severityStyles(severity: Severity) {
  switch (severity) {
    case "critical":
      return {
        badge: "bg-status-error/8 text-severity-critical border-status-error/25",
        border: "border-l-severity-critical",
        dot: "bg-severity-critical",
        text: "text-severity-critical",
        bar: "bg-severity-critical",
      };
    case "high":
      return {
        badge: "bg-severity-high/8 text-severity-high border-severity-high/25",
        border: "border-l-severity-high",
        dot: "bg-severity-high",
        text: "text-severity-high",
        bar: "bg-severity-high",
      };
    case "medium":
      return {
        badge: "bg-severity-medium/8 text-severity-medium border-severity-medium/25",
        border: "border-l-severity-medium",
        dot: "bg-severity-medium",
        text: "text-severity-medium",
        bar: "bg-severity-medium",
      };
    case "low":
      return {
        badge: "bg-severity-low/8 text-severity-low border-severity-low/25",
        border: "border-l-severity-low",
        dot: "bg-severity-low",
        text: "text-severity-low",
        bar: "bg-severity-low",
      };
    case "info":
    default:
      return {
        badge: "bg-surface-2 text-severity-info border-border",
        border: "border-l-severity-info",
        dot: "bg-severity-info",
        text: "text-severity-info",
        bar: "bg-severity-info",
      };
  }
}

export function scoreTone(score: number | null) {
  if (score === null) {
    return {
      value: "text-text-muted",
      bar: "bg-border",
      label: "text-text-muted",
      qualifier: "Not available",
    };
  }
  if (score >= 80) {
    return {
      value: "text-status-success",
      bar: "bg-status-success",
      label: "text-status-success",
      qualifier: "Healthy",
    };
  }
  if (score >= 60) {
    return {
      value: "text-text-primary",
      bar: "bg-accent",
      label: "text-text-secondary",
      qualifier: "Moderate",
    };
  }
  if (score >= 40) {
    return {
      value: "text-severity-medium",
      bar: "bg-severity-medium",
      label: "text-severity-medium",
      qualifier: "At risk",
    };
  }
  return {
    value: "text-severity-critical",
    bar: "bg-severity-critical",
    label: "text-severity-critical",
    qualifier: "Critical",
  };
}

export function vibeDebtTone(score: number | null) {
  // Vibe debt: higher = more debt. Invert semantics.
  if (score === null) {
    return { value: "text-text-muted", bar: "bg-border", qualifier: "Not available" };
  }
  if (score <= 20) {
    return { value: "text-status-success", bar: "bg-status-success", qualifier: "Low technical risk" };
  }
  if (score <= 40) {
    return { value: "text-text-primary", bar: "bg-severity-low", qualifier: "Moderate" };
  }
  if (score <= 60) {
    return { value: "text-severity-medium", bar: "bg-severity-medium", qualifier: "Elevated" };
  }
  return { value: "text-severity-critical", bar: "bg-severity-critical", qualifier: "High technical debt" };
}
