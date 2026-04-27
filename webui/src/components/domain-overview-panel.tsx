"use client";

import { useQuery } from "@tanstack/react-query";
import { LeaderboardTable } from "@/components/leaderboard-table";
import type { DomainOverview, LeaderboardRow } from "@/lib/types";

type Props = {
  domain: string;
};

export function DomainOverviewPanel({ domain }: Props) {
  const { data } = useQuery({
    queryKey: ["domain", domain, "overview"],
    queryFn: async () => {
      const res = await fetch(`/api/domains/${domain}/overview`);
      return res.json();
    },
  });

  const { data: capData } = useQuery({
    queryKey: ["domain", domain, "leaderboard", "capability"],
    queryFn: async () => {
      const res = await fetch(`/api/domains/${domain}/leaderboard?type=capability`);
      return res.json();
    },
  });

  const { data: safetyData } = useQuery({
    queryKey: ["domain", domain, "leaderboard", "safety"],
    queryFn: async () => {
      const res = await fetch(`/api/domains/${domain}/leaderboard?type=safety`);
      return res.json();
    },
  });

  const overview: DomainOverview | null = data ?? null;
  const capRows: LeaderboardRow[] = capData?.items ?? [];
  const safetyRows: LeaderboardRow[] = safetyData?.items ?? [];

  if (!overview) {
    return <p className="text-muted-foreground">No data for this domain.</p>;
  }

  const domainLabel = domain.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div>
      <h2 className="mb-4 text-2xl font-bold">{domainLabel}</h2>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <div className="rounded-lg border p-4 text-center">
          <div className="text-3xl font-bold text-blue-600">{overview.capability_score.toFixed(2)}</div>
          <div className="text-sm text-muted-foreground">Capability Score</div>
        </div>
        <div className="rounded-lg border p-4 text-center">
          <div className="text-3xl font-bold text-green-600">{overview.safety_score.toFixed(2)}</div>
          <div className="text-sm text-muted-foreground">Safety Score</div>
        </div>
        <div className="rounded-lg border p-4 text-center">
          <div className={`text-3xl font-bold ${overview.risk_index > 0.5 ? "text-red-600" : "text-yellow-600"}`}>
            {overview.risk_index.toFixed(2)}
          </div>
          <div className="text-sm text-muted-foreground">Risk Index</div>
        </div>
      </div>

      {capRows.length > 0 && (
        <div className="mb-6">
          <LeaderboardTable rows={capRows} title="Capability Leaderboard" />
        </div>
      )}

      {safetyRows.length > 0 && (
        <div className="mb-6">
          <LeaderboardTable rows={safetyRows} title="Safety Leaderboard" />
        </div>
      )}
    </div>
  );
}
