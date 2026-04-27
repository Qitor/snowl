"use client";

import type { LeaderboardRow } from "@/lib/types";

type Props = {
  rows: LeaderboardRow[];
  title?: string;
};

export function LeaderboardTable({ rows, title }: Props) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">No leaderboard data.</p>;
  }

  return (
    <div>
      {title && <h3 className="mb-2 text-sm font-semibold">{title}</h3>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2 pr-4 font-medium">#</th>
              <th className="pb-2 pr-4 font-medium">Model</th>
              <th className="pb-2 pr-4 font-medium text-right">Score</th>
              <th className="pb-2 pr-4 font-medium text-right">Benchmarks</th>
              {rows[0]?.model_metadata && (
                <>
                  <th className="pb-2 pr-4 font-medium">Company</th>
                  <th className="pb-2 pr-4 font-medium">Source</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={`${row.model}-${row.domain}-${row.benchmark_type}`} className="border-b last:border-0">
                <td className="py-2 pr-4 font-mono">{row.rank || i + 1}</td>
                <td className="py-2 pr-4 font-medium">{row.model}</td>
                <td className="py-2 pr-4 text-right font-mono">{row.primary_metric_mean.toFixed(3)}</td>
                <td className="py-2 pr-4 text-right">{row.benchmarks_evaluated}</td>
                {row.model_metadata && (
                  <>
                    <td className="py-2 pr-4 text-muted-foreground">{row.model_metadata.company || "—"}</td>
                    <td className="py-2 pr-4 text-muted-foreground">{row.model_metadata.source_type || "—"}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
