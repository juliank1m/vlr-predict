"use client";

import { useEffect, useState } from "react";

// Singleton cache — loaded once, shared across all TeamLogo instances
let logoMap: Record<string, string> | null = null;
let logoPromise: Promise<Record<string, string>> | null = null;

function getLogoMap(): Promise<Record<string, string>> {
  if (logoMap) return Promise.resolve(logoMap);
  if (!logoPromise) {
    logoPromise = fetch("/team-logos.json")
      .then((r) => r.json() as Promise<Record<string, string>>)
      .then((data) => {
        logoMap = data;
        return data;
      })
      .catch(() => {
        logoMap = {};
        return {};
      });
  }
  return logoPromise;
}

interface TeamLogoProps {
  name: string;
  logoUrl?: string | null;
  size?: number;
  className?: string;
}

export function TeamLogo({ name, logoUrl, size = 24, className = "" }: TeamLogoProps) {
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(logoUrl ?? null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (logoUrl) {
      setResolvedUrl(logoUrl);
      return;
    }
    // Look up from static JSON
    if (logoMap) {
      setResolvedUrl(logoMap[name] ?? null);
    } else {
      getLogoMap().then((map) => setResolvedUrl(map[name] ?? null));
    }
  }, [name, logoUrl]);

  if (resolvedUrl && !failed) {
    return (
      <img
        src={resolvedUrl}
        alt={name}
        width={size}
        height={size}
        className={`inline-block rounded-sm object-contain drop-shadow-[0_0_1px_rgba(255,255,255,0.8)] ${className}`}
        onError={() => setFailed(true)}
      />
    );
  }

  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();

  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;

  return (
    <span
      className={`inline-flex items-center justify-center font-bold uppercase tracking-wider border border-white/10 ${className}`}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.32,
        background: `linear-gradient(135deg, oklch(0.35 0.08 ${hue}), oklch(0.22 0.05 ${hue}))`,
        color: `oklch(0.85 0.1 ${hue})`,
      }}
    >
      {initials}
    </span>
  );
}
