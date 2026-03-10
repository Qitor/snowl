import { ComparePage } from "@/components/compare-page";
import { QueryProvider } from "@/components/providers/query-provider";

export default function CompareRoutePage() {
  return (
    <QueryProvider>
      <ComparePage />
    </QueryProvider>
  );
}
