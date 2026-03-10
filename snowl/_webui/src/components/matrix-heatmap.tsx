"use client";

import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";

type MatrixHeatmapProps = {
  matrix: Record<string, Record<string, number>>;
  rowLabel: string;
  colLabel: string;
};

export function MatrixHeatmap({ matrix, rowLabel, colLabel }: MatrixHeatmapProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  const payload = useMemo(() => {
    const rows = Object.keys(matrix).sort();
    const colSet = new Set<string>();
    for (const row of rows) {
      for (const col of Object.keys(matrix[row] || {})) {
        colSet.add(col);
      }
    }
    const cols = Array.from(colSet).sort();

    const values: Array<[number, number, number]> = [];
    for (const rowName of rows) {
      for (const colName of cols) {
        const rowIdx = rows.indexOf(rowName);
        const colIdx = cols.indexOf(colName);
        const value = Number(matrix[rowName]?.[colName]);
        if (Number.isFinite(value)) {
          values.push([colIdx, rowIdx, value]);
        }
      }
    }

    return { rows, cols, values };
  }, [matrix]);

  useEffect(() => {
    if (!rootRef.current) {
      return;
    }
    const chart = echarts.init(rootRef.current);
    chart.setOption({
      animation: true,
      tooltip: {
        position: "top",
        formatter(params: { data: [number, number, number] }) {
          const [x, y, value] = params.data;
          return `${payload.rows[y]} × ${payload.cols[x]}<br/>score: ${value.toFixed(4)}`;
        },
      },
      grid: {
        top: 10,
        left: 110,
        right: 30,
        bottom: 70,
      },
      xAxis: {
        type: "category",
        data: payload.cols,
        name: colLabel,
        nameLocation: "center",
        nameGap: 52,
        splitArea: { show: true },
      },
      yAxis: {
        type: "category",
        data: payload.rows,
        name: rowLabel,
        nameLocation: "center",
        nameGap: 85,
        splitArea: { show: true },
      },
      visualMap: {
        min: 0,
        max: 1,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 10,
        inRange: {
          color: ["#e2f4f1", "#88d3c8", "#0f8575"],
        },
      },
      series: [
        {
          name: "score",
          type: "heatmap",
          data: payload.values,
          label: {
            show: true,
            formatter: ({ data }: { data: [number, number, number] }) => data[2].toFixed(2),
            color: "#07332d",
            fontSize: 10,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 12,
              shadowColor: "rgba(0, 0, 0, 0.15)",
            },
          },
        },
      ],
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [payload, rowLabel, colLabel]);

  return <div ref={rootRef} className="h-[330px] w-full" />;
}
