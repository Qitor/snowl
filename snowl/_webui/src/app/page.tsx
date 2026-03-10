import { RunGalleryPage } from "@/components/run-gallery-page";
import { QueryProvider } from "@/components/providers/query-provider";

export default function HomePage() {
  return (
    <QueryProvider>
      <RunGalleryPage />
    </QueryProvider>
  );
}
