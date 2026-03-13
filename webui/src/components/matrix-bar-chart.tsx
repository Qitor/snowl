"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

import { cn } from "@/lib/utils";

type MatrixBarChartProps = {
  matrix: Record<string, Record<string, number>>;
  matrixByMetric?: Record<string, Record<string, Record<string, number>>>;
  metricOrder?: string[];
  rowLabel: string;
  seriesLabel: string;
};

function humanizeMetricName(metric: string): string {
  return metric
    .replace(/[._]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.slice(0, 1).toUpperCase() + word.slice(1))
    .join(" ");
}

export function MatrixBarChart({ matrix, matrixByMetric, metricOrder, rowLabel, seriesLabel }: MatrixBarChartProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const availableMetrics = useMemo(() => {
    const byMetric = matrixByMetric || {};
    const keys = Object.keys(byMetric).filter((metric) => {
      const rows = byMetric[metric] || {};
      return Object.keys(rows).length > 0;
    });
    if (keys.length === 0) {
      return [];
    }
    const order = Array.isArray(metricOrder) ? metricOrder : [];
    return keys.slice().sort((lhs, rhs) => {
      const lhsIdx = order.indexOf(lhs);
      const rhsIdx = order.indexOf(rhs);
      if (lhsIdx >= 0 && rhsIdx >= 0) {
        return lhsIdx - rhsIdx;
      }
      if (lhsIdx >= 0) {
        return -1;
      }
      if (rhsIdx >= 0) {
        return 1;
      }
      return lhs.localeCompare(rhs);
    });
  }, [matrixByMetric, metricOrder]);
  const [activeMetric, setActiveMetric] = useState<string>("");

  useEffect(() => {
    if (availableMetrics.length === 0) {
      if (activeMetric !== "") {
        setActiveMetric("");
      }
      return;
    }
    if (!activeMetric || !availableMetrics.includes(activeMetric)) {
      setActiveMetric(availableMetrics[0]);
    }
  }, [availableMetrics, activeMetric]);

  const activeMatrix = useMemo(() => {
    if (availableMetrics.length === 0 || !activeMetric) {
      return matrix;
    }
    return (matrixByMetric?.[activeMetric] || {}) as Record<string, Record<string, number>>;
  }, [availableMetrics.length, activeMetric, matrixByMetric, matrix]);

  const payload = useMemo(() => {
    const rows = Object.keys(activeMatrix).sort();
    const seriesSet = new Set<string>();
    for (const row of rows) {
      for (const col of Object.keys(activeMatrix[row] || {})) {
        seriesSet.add(col);
      }
    }
    const seriesNames = Array.from(seriesSet).sort();
    const series = seriesNames.map((name) => ({
      name,
      type: "bar" as const,
      barMaxWidth: 28,
      label: {
        show: true,
        position: "right" as const,
        formatter: ({ value }: { value: number }) => value.toFixed(2),
        color: "#10322d",
        fontSize: 11,
      },
      emphasis: {
        focus: "series" as const,
      },
      data: rows.map((row) => {
        const value = Number(activeMatrix[row]?.[name]);
        return Number.isFinite(value) ? value : 0;
      }),
    }));
    return { rows, seriesNames, series };
  }, [activeMatrix]);

  const xAxisLabel = activeMetric ? humanizeMetricName(activeMetric) : "Score";

  useEffect(() => {
    if (!rootRef.current) {
      return;
    }
    const chart = echarts.init(rootRef.current);
    chart.setOption({
      animation: true,
      color: ["#0f766e", "#34d399", "#0891b2", "#14b8a6", "#65a30d", "#f59e0b"],
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "shadow",
        },
        formatter(params: Array<{ axisValue: string; seriesName: string; value: number }>) {
          const lines = params
            .filter((item) => Number.isFinite(item.value))
            .map((item) => `${item.seriesName}: ${item.value.toFixed(4)}`);
          return `${params[0]?.axisValue || ""}<br/>${lines.join("<br/>")}`;
        },
      },
      legend: {
        top: 0,
        type: "scroll",
        textStyle: {
          fontSize: 12,
        },
      },
      grid: {
        top: payload.seriesNames.length > 1 ? 56 : 20,
        left: 180,
        right: 36,
        bottom: 24,
      },
      xAxis: {
        type: "value",
        min: 0,
        max: 1,
        name: xAxisLabel,
        nameLocation: "middle",
        nameGap: 38,
        splitLine: {
          lineStyle: {
            color: "rgba(15, 118, 110, 0.12)",
          },
        },
      },
      yAxis: {
        type: "category",
        data: payload.rows,
        axisLabel: {
          width: 160,
          overflow: "truncate",
          fontSize: 11,
        },
      },
      series: payload.series,
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [payload, rowLabel, seriesLabel, xAxisLabel]);

  return (
    <div className="space-y-3">
      {availableMetrics.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {availableMetrics.map((metricName) => (
            <button
              key={metricName}
              type="button"
              onClick={() => setActiveMetric(metricName)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm transition",
                activeMetric === metricName
                  ? "border-primary bg-primary text-primary-foreground shadow-sm"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
              )}
            >
              {humanizeMetricName(metricName)}
            </button>
          ))}
        </div>
      ) : null}
      {payload.rows.length === 0 ? (
        <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          暂无矩阵数据。等待至少一个已打分 trial 后，这里会显示按 {seriesLabel} 分组的柱状图。
        </div>
      ) : null}
      <div ref={rootRef} className="h-[360px] w-full" />
    </div>
  );
}
