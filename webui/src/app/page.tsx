import { RiskMonitorPage } from "@/components/risk-monitor-page";
import { QueryProvider } from "@/components/providers/query-provider";

export default function HomePage() {
  return (
    <QueryProvider>
      <RiskMonitorPage />
    </QueryProvider>
  );
}
