"use client";

import { TeamLogo } from "@/components/team-logo";

interface WinProbBarProps {
  team1Name: string;
  team2Name: string;
  team1Prob: number;
}

export function WinProbBar({
  team1Name,
  team2Name,
  team1Prob,
}: WinProbBarProps) {
  const pct1 = Math.round(team1Prob * 100);
  const pct2 = 100 - pct1;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm font-medium">
        <span className="flex items-center gap-1.5">
          <TeamLogo name={team1Name} size={16} />
          {team1Name} <span className="text-muted-foreground">{pct1}%</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-muted-foreground">{pct2}%</span> {team2Name}
          <TeamLogo name={team2Name} size={16} />
        </span>
      </div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="bg-primary transition-all duration-300"
          style={{ width: `${pct1}%` }}
        />
        <div
          className="bg-accent transition-all duration-300"
          style={{ width: `${pct2}%` }}
        />
      </div>
    </div>
  );
}
