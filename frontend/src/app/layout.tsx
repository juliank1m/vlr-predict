import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Crosshair, Swords, ChartNoAxesCombined, List } from "lucide-react";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "VLR Predict",
  description:
    "Pre-match win probability predictions for professional Valorant.",
};

const navLinks = [
  { href: "/", label: "Predictions", icon: Crosshair },
  { href: "/compare", label: "Head-to-Head", icon: Swords },
  { href: "/model", label: "Model", icon: ChartNoAxesCombined },
  { href: "/matches", label: "Matches", icon: List },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
    >
      <body className="min-h-full flex flex-col">
        <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="mx-auto flex h-14 max-w-6xl items-center px-4">
            <Link href="/" className="mr-8 font-bold text-lg tracking-tight">
              VLR Predict
            </Link>
            <nav className="flex items-center gap-6 text-sm">
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground"
                >
                  <link.icon size={14} />
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1">
          <div className="mx-auto max-w-6xl px-4 py-8">{children}</div>
        </main>
      </body>
    </html>
  );
}
