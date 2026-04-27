import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: { domain: string } }) {
  const store = getMonitorStore();
  const overview = store.domainOverview(context.params.domain);
  if (!overview) {
    return NextResponse.json({ error: "domain_not_found" }, { status: 404 });
  }
  return NextResponse.json(overview);
}
