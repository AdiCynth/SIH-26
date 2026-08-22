"use client";

type Option<T extends string> = { value: T; label: string; hint?: string };

type SegmentedControlProps<T extends string> = {
  value: T;
  onChange: (value: T) => void;
  options: Option<T>[];
  label?: string;
  disabled?: boolean;
  className?: string;
};

export default function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
  disabled = false,
  className = "",
}: SegmentedControlProps<T>) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className={`inline-flex items-center rounded-[4px] border border-border bg-surface-2 p-0.5 ${className}`}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            type="button"
            aria-selected={active}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={`inline-flex h-7 items-center rounded-[3px] px-3 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:cursor-not-allowed disabled:opacity-55 ${
              active
                ? "bg-white text-text-primary shadow-[0_1px_0_rgba(22,26,23,0.05),0_0_0_1px_rgba(22,26,23,0.06)]"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
