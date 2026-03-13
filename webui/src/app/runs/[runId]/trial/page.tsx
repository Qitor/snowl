import { QueryProvider } from "@/components/providers/query-provider";
import { RunTrialDetailPage } from "@/components/run-trial-detail-page";

export default function RunTrialPage({ params }: { params: { runId: string } }) {
  return (
    <QueryProvider>
      <RunTrialDetailPage runId={params.runId} />
    </QueryProvider>
  );
}
