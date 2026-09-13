import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cold Chain Sentinel — Autonomous Voice Telephony & Compliance Cockpit",
  description:
    "Real-time operations console monitoring reefer temperature excursions, CALL-E driver interrogation, and autonomous fleet actuation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col">
        {children}
      </body>
    </html>
  );
}
