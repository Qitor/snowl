import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function encodeSse(event: Record<string, unknown>): string {
  const eventId = String(event.event_id || "");
  const lines: string[] = [];
  if (eventId) {
    lines.push(`id: ${eventId}`);
  }
  lines.push("event: runtime");
  lines.push(`data: ${JSON.stringify(event)}`);
  return `${lines.join("\n")}\n\n`;
}

export async function GET(request: Request, context: { params: { runId: string } }) {
  const store = getMonitorStore();
  const runId = context.params.runId;
  const snapshot = store.runSnapshot(runId);
  if (!snapshot) {
    return new Response(JSON.stringify({ detail: `run not found: ${runId}` }), {
      status: 404,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }

  const url = new URL(request.url);
  const cursor = request.headers.get("last-event-id") || url.searchParams.get("last_event_id") || undefined;

  const encoder = new TextEncoder();

  let closed = false;
  let keepaliveTimer: NodeJS.Timeout | null = null;
  let unsubscribe: (() => void) | null = null;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const safeEnqueue = (chunk: string) => {
        if (closed) {
          return;
        }
        try {
          controller.enqueue(encoder.encode(chunk));
        } catch {
          closed = true;
        }
      };

      const backlog = store.backfillEvents({ runId, lastEventId: cursor, limit: 1000 });
      for (const event of backlog) {
        safeEnqueue(encodeSse(event));
      }

      unsubscribe = store.subscribe(runId, (event) => {
        safeEnqueue(encodeSse(event));
      });

      keepaliveTimer = setInterval(() => {
        safeEnqueue(": keepalive\n\n");
      }, 10_000);

      request.signal.addEventListener("abort", () => {
        if (closed) {
          return;
        }
        closed = true;
        if (keepaliveTimer) {
          clearInterval(keepaliveTimer);
          keepaliveTimer = null;
        }
        if (unsubscribe) {
          unsubscribe();
          unsubscribe = null;
        }
        try {
          controller.close();
        } catch {
          // ignore close race
        }
      });
    },
    cancel() {
      closed = true;
      if (keepaliveTimer) {
        clearInterval(keepaliveTimer);
        keepaliveTimer = null;
      }
      if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
