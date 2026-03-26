"use client";

import { useState } from "react";
import { User } from "lucide-react";
import { getAgentIconUrl } from "@/lib/assets";

interface AgentIconProps {
  agentName: string | null | undefined;
  size?: number;
  className?: string;
}

export function AgentIcon({ agentName, size = 20, className = "" }: AgentIconProps) {
  const [failed, setFailed] = useState(false);
  const url = getAgentIconUrl(agentName);

  if (url && !failed) {
    return (
      <img
        src={url}
        alt={agentName ?? "Agent"}
        width={size}
        height={size}
        className={`inline-block rounded object-cover ${className}`}
        onError={() => setFailed(true)}
      />
    );
  }

  return <User size={size} className={`inline-block text-muted-foreground ${className}`} />;
}
