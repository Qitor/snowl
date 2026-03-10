"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef } from "react";

import type { RuntimeEvent } from "@/lib/types";

type VirtualLogViewerProps = {
  events: RuntimeEvent[];
};

function eventToLine(event: RuntimeEvent): string {
  const ts = typeof event.ts_ms === "number" ? new Date(event.ts_ms).toLocaleTimeString() : "--:--:--";
  const id = String(event.event_id || "");
  const name = String(event.event || "runtime");
  const taskId = String(event.task_id || "-");
  const agentId = String(event.agent_id || "-");
  const variantId = String(event.variant_id || "default");
  const model = String(event.model || "").trim();
  const message = String(event.message || "");
  return `[${ts}] [${id}] ${name} task=${taskId} agent=${agentId} variant=${variantId}${model ? ` model=${model}` : ""} ${message}`.trim();
}

export function VirtualLogViewer({ events }: VirtualLogViewerProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const items = useMemo(() => events.map(eventToLine), [events]);

  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 34,
    overscan: 18,
  });

  return (
    <div
      ref={parentRef}
      className="h-[420px] overflow-auto rounded-[24px] border border-slate-900/70 bg-[#071019] p-3 font-[family-name:var(--font-mono)] text-[13px] leading-7 text-cyan-100 shadow-inner"
    >
      <div
        style={{
          height: `${rowVirtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {rowVirtualizer.getVirtualItems().map((row) => {
          const line = items[row.index] ?? "";
          return (
            <div
              key={row.key}
              className="absolute left-0 top-0 w-full whitespace-pre-wrap break-all border-b border-slate-800/50 px-3 py-1.5"
              style={{ transform: `translateY(${row.start}px)` }}
            >
              {line}
            </div>
          );
        })}
      </div>
    </div>
  );
}
