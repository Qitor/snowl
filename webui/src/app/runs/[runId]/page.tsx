import { QueryProvider } from "@/components/providers/query-provider";
import { RunWorkspacePage } from "@/components/run-workspace-page";

export default function RunPage({ params }: { params: { runId: string } }) {
  return (
    <QueryProvider>
      <RunWorkspacePage runId={params.runId} />
    </QueryProvider>
  );
}
