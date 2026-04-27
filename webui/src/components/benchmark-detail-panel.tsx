"use client";

import { useQuery } from "@tanstack/react-query";
import type { BenchmarkSummary } from "@/lib/types";

type Props = {
  benchmarkName: string;
};

export function BenchmarkDetailPanel({ benchmarkName }: Props) {
  const { data } = useQuery({
    queryKey: ["benchmark", benchmarkName],
    queryFn: async () => {
      const res = await fetch(`/api/benchmarks/${benchmarkName}`);
      return res.json();
    },
  });

  const detail: BenchmarkSummary | null = data ?? null;

  if (!detail) {
    return <p className="text-muted-foreground">No data for this benchmark.</p>;
  }

  return (
    <div className="rounded-lg border p-5">
      <h3 className="mb-3 text-lg font-semibold">{detail.display_name}</h3>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Domain</dt>
        <dd>{detail.domain.replace(/_/g, " ")}</dd>
        <dt className="text-muted-foreground">Type</dt>
        <dd>{detail.benchmark_type}</dd>
        <dt className="text-muted-foreground">Family</dt>
        <dd>{detail.family}</dd>
        <dt className="text-muted-foreground">Primary Metric</dt>
        <dd>{detail.primary_metric}</dd>
        <dt className="text-muted-foreground">Higher is Better</dt>
        <dd>{detail.higher_is_better ? "Yes" : "No"}</dd>
        <dt className="text-muted-foreground">Models Evaluated</dt>
        <dd>{detail.models_evaluated}</dd>
      </dl>
      {detail.dashboard_tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {detail.dashboard_tags.map((tag) => (
            <span key={tag} className="rounded-full bg-muted px-2 py-0.5 text-xs">
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
