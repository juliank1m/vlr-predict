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
    .slice(0, 2)
    .toUpperCase();

  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;

  return (
    <span
      className={`inline-flex items-center justify-center rounded-sm text-white font-bold ${className}`}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.4,
        backgroundColor: `oklch(0.55 0.15 ${hue})`,
      }}
    >
      {initials}
    </span>
  );
}
