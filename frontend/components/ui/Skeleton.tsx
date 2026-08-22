type SkeletonProps = {
  className?: string;
};

export default function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      className={`animate-skeleton rounded-[3px] bg-surface-3 ${className}`}
      aria-hidden
    />
  );
}

export function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <tr className="border-b border-border-subtle">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-3.5 w-full" />
        </td>
      ))}
    </tr>
  );
}

export function ScanPageSkeleton() {
  return (
    <div className="flex flex-col gap-6 animate-fade-in" aria-busy aria-label="Loading scan">
      <Skeleton className="h-3.5 w-32" />
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-3.5 w-56" />
      </div>
      <div className="grid grid-cols-4 gap-6 border-y border-border-subtle py-5">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-2">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-6 w-24" />
          </div>
        ))}
      </div>
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-10 animate-fade-in" aria-busy aria-label="Loading dashboard">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-3.5 w-40" />
        <Skeleton className="h-7 w-96" />
      </div>
      <Skeleton className="h-12 w-full" />
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-40" />
      </div>
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </div>
    </div>
  );
}
