import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";

import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Snowl Monitor",
  description: "Snowl evaluation and risk monitoring dashboard",
};

function NavHeader() {
  return (
    <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-12 max-w-7xl items-center gap-6 px-4">
        <a href="/" className="text-sm font-semibold tracking-tight">
          Snowl
        </a>
        <nav className="flex items-center gap-4 text-sm">
          <a href="/" className="text-muted-foreground hover:text-foreground transition-colors">
            Dashboard
          </a>
          <a href="/runs" className="text-muted-foreground hover:text-foreground transition-colors">
            Runs
          </a>
          <a href="/compare" className="text-muted-foreground hover:text-foreground transition-colors">
            Compare
          </a>
        </nav>
      </div>
    </header>
  );
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${sans.variable} ${mono.variable} font-[family-name:var(--font-sans)]`}>
        <NavHeader />
        {children}
      </body>
    </html>
  );
}
