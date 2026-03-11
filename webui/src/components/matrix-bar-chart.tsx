"use client";

import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";

type MatrixBarChartProps = {
  matrix: Record<string, Record<string, number>>;
  rowLabel: string;
  seriesLabel: string;
};

export function MatrixBarChart({ matrix, rowLabel, seriesLabel }: MatrixBarChartProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  const payload = useMemo(() => {
    const rows = Object.keys(matrix).sort();
    const seriesSet = new Set<string>();
    for (const row of rows) {
      for (const col of Object.keys(matrix[row] || {})) {
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
        const value = Number(matrix[row]?.[name]);
        return Number.isFinite(value) ? value : 0;
      }),
    }));
    return { rows, seriesNames, series };
  }, [matrix]);

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
        name: "Score",
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
        name: rowLabel,
        nameLocation: "middle",
        nameGap: 120,
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
  }, [payload, rowLabel, seriesLabel]);

  return (
    <div className="space-y-3">
      {payload.rows.length === 0 ? (
        <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          暂无矩阵数据。等待至少一个已打分 trial 后，这里会显示按 {seriesLabel} 分组的柱状图。
        </div>
      ) : null}
      <div ref={rootRef} className="h-[360px] w-full" />
    </div>
  );
}
