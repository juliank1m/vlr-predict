import type { Metadata } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import { Crosshair, Swords, ChartNoAxesCombined, List } from "lucide-react";
import Link from "next/link";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Val Predict",
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
      className={`${dmSans.variable} ${jetbrainsMono.variable} h-full antialiased dark`}
    >
      <body className="min-h-full flex flex-col">
        <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="mx-auto flex h-11 max-w-6xl items-center px-4">
            <Link href="/" className="mr-8 font-bold text-sm tracking-[0.2em] uppercase text-primary">
              Val<span className="text-foreground">/</span>Predict
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
          <div className="mx-auto max-w-6xl px-4 py-6">{children}</div>
        </main>
      </body>
    </html>
  );
}
