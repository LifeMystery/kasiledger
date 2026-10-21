import type { Metadata } from "next";
import "./globals.css";
import { BusinessProvider } from "@/components/BusinessContext";
import TopBar from "@/components/TopBar";

export const metadata: Metadata = {
  title: "KasiLedger",
  description: "Voice-first bookkeeping and business verification for informal businesses",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,650;12..96,750&family=Source+Sans+3:wght@400;600;700&display=swap"
        />
      </head>
      <body>
        <BusinessProvider>
          <TopBar />
          {children}
        </BusinessProvider>
      </body>
    </html>
  );
}
