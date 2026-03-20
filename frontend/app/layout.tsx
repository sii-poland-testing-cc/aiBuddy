import type { Metadata } from "next";
import { DM_Sans, DM_Mono } from "next/font/google";
import "@llamaindex/chat-ui/styles/markdown.css";
import "./globals.css";
import ErrorBoundary from "@/components/ErrorBoundary";
import { ProjectOperationsProvider } from "@/lib/ProjectOperationsContext";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["300", "400", "500", "600"],
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-dm-mono",
});

export const metadata: Metadata = {
  title: "AI Buddy",
  description: "QA Agent Platform — Test Suite Audit & Optimization",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${dmSans.variable} ${dmMono.variable}`}>
      <body><ProjectOperationsProvider><ErrorBoundary>{children}</ErrorBoundary></ProjectOperationsProvider></body>
    </html>
  );
}
