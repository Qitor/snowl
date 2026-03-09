import { Dashboard } from "@/components/dashboard";
import { QueryProvider } from "@/components/providers/query-provider";

export default function HomePage() {
  return (
    <QueryProvider>
      <Dashboard />
    </QueryProvider>
  );
}
