"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import type { DomainOverview, BenchmarkSummary, LeaderboardRow } from "@/lib/types";

export function RiskMonitorPage() {
  const { data: domainsData, isLoading: domainsLoading } = useQuery({
    queryKey: ["domains"],
    queryFn: async () => {
      const res = await fetch("/api/domains");
      return res.json();
    },
  });

  const { data: benchmarksData } = useQuery({
    queryKey: ["benchmarks"],
    queryFn: async () => {
      const res = await fetch("/api/benchmarks");
      return res.json();
    },
  });

  const domains: DomainOverview[] = domainsData?.items ?? [];
  const benchmarks: BenchmarkSummary[] = benchmarksData?.items ?? [];

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Evaluation Dashboard</h1>
          <p className="mt-2 text-muted-foreground">
            Model capability and safety evaluation across risk domains
          </p>
        </div>

        {/* Domain Cards */}
        <section className="mb-10">
          <h2 className="mb-4 text-xl font-semibold">Domains</h2>
          {domainsLoading ? (
            <p className="text-muted-foreground">Loading domains...</p>
          ) : domains.length === 0 ? (
            <p className="text-muted-foreground">
              No evaluation data yet. Run a benchmark to see results here.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {domains.map((domain) => (
                <DomainCard key={domain.domain} domain={domain} />
              ))}
            </div>
          )}
        </section>

        {/* Benchmark Navigator */}
        <section className="mb-10">
          <h2 className="mb-4 text-xl font-semibold">Benchmarks</h2>
          {benchmarks.length === 0 ? (
            <p className="text-muted-foreground">No benchmark data available.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {benchmarks.map((bench) => (
                <BenchmarkCard key={bench.name} benchmark={bench} />
              ))}
            </div>
          )}
        </section>

        {/* Quick Access */}
        <section>
          <h2 className="mb-4 text-xl font-semibold">Run Monitor</h2>
          <a
            href="/runs"
            className="text-blue-600 hover:text-blue-800 underline"
          >
            View all runs &rarr;
          </a>
        </section>
      </div>
    </div>
  );
}

function DomainCard({ domain }: { domain: DomainOverview }) {
  const domainLabel = domain.domain.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <Card className="cursor-pointer transition-shadow hover:shadow-md">
      <CardHeader>
        <CardTitle className="text-lg">{domainLabel}</CardTitle>
        <CardDescription>
          {domain.benchmark_count} benchmark{domain.benchmark_count !== 1 ? "s" : ""} &middot;{" "}
          {domain.model_count} model{domain.model_count !== 1 ? "s" : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-2xl font-bold text-blue-600">
              {domain.capability_score.toFixed(2)}
            </div>
            <div className="text-xs text-muted-foreground">Capability</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-green-600">
              {domain.safety_score.toFixed(2)}
            </div>
            <div className="text-xs text-muted-foreground">Safety</div>
          </div>
          <div>
            <div className={`text-2xl font-bold ${domain.risk_index > 0.5 ? "text-red-600" : "text-yellow-600"}`}>
              {domain.risk_index.toFixed(2)}
            </div>
            <div className="text-xs text-muted-foreground">Risk Index</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function BenchmarkCard({ benchmark }: { benchmark: BenchmarkSummary }) {
  const typeColor = benchmark.benchmark_type === "safety" ? "text-orange-600" : "text-blue-600";
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{benchmark.display_name}</CardTitle>
        <CardDescription className={typeColor}>
          {benchmark.benchmark_type} &middot; {benchmark.domain.replace(/_/g, " ")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-xs text-muted-foreground">
          Metric: {benchmark.primary_metric}
        </div>
      </CardContent>
    </Card>
  );
}
