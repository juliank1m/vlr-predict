"use client";

import { useEffect, useState } from "react";
import { getAllMapSplashUrls } from "@/lib/assets";

export function MapBackground() {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const urls = getAllMapSplashUrls();
    setUrl(urls[Math.floor(Math.random() * urls.length)]);
  }, []);

  if (!url) return null;

  return (
    <div
      className="fixed inset-0 z-0 pointer-events-none"
      style={{
        backgroundImage: `url(${url})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div className="absolute inset-0 bg-background/90 backdrop-blur-sm" />
    </div>
  );
}
