"use client";

import { useQuery } from "@tanstack/react-query";
import type { BenchmarkSample } from "@/lib/types";

type Props = {
  benchmarkName: string;
  open: boolean;
  onClose: () => void;
};

export function BenchmarkSampleDrawer({ benchmarkName, open, onClose }: Props) {
  const { data } = useQuery({
    queryKey: ["benchmark", benchmarkName, "samples"],
    queryFn: async () => {
      const res = await fetch(`/api/benchmarks/${benchmarkName}/samples`);
      return res.json();
    },
    enabled: open,
  });

  const samples: BenchmarkSample[] = data?.items ?? [];

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-lg overflow-y-auto bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Samples: {benchmarkName}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            Close
          </button>
        </div>
        {samples.length === 0 ? (
          <p className="text-sm text-muted-foreground">No samples available.</p>
        ) : (
          <div className="space-y-3">
            {samples.map((sample) => (
              <div key={sample.id} className="rounded-lg border p-3">
                <div className="mb-1 text-xs font-mono text-muted-foreground">{sample.id}</div>
                <p className="text-sm">{sample.input_preview}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
