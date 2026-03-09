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
  const message = String(event.message || "");
  return `[${ts}] [${id}] ${name} task=${taskId} agent=${agentId} ${message}`.trim();
}

export function VirtualLogViewer({ events }: VirtualLogViewerProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const items = useMemo(() => events.map(eventToLine), [events]);

  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 22,
    overscan: 18,
  });

  return (
    <div
      ref={parentRef}
      className="h-[320px] overflow-auto rounded-md border border-slate-900/70 bg-[#071019] p-2 font-[family-name:var(--font-mono)] text-[11px] text-cyan-100"
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
              className="absolute left-0 top-0 w-full whitespace-pre-wrap break-all border-b border-slate-800/50 px-1 py-0.5"
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
