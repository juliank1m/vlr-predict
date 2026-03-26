"use client";

import { useState } from "react";

interface TeamLogoProps {
  name: string;
  logoUrl?: string | null;
  size?: number;
  className?: string;
}

export function TeamLogo({ name, logoUrl, size = 24, className = "" }: TeamLogoProps) {
  const [failed, setFailed] = useState(false);

  if (logoUrl && !failed) {
    return (
      <img
        src={logoUrl}
        alt={name}
        width={size}
        height={size}
        className={`inline-block rounded-sm object-contain ${className}`}
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
