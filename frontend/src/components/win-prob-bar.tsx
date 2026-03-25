"use client";

interface WinProbBarProps {
  team1Name: string;
  team2Name: string;
  team1Prob: number;
}

export function WinProbBar({ team1Name, team2Name, team1Prob }: WinProbBarProps) {
  const pct1 = Math.round(team1Prob * 100);
  const pct2 = 100 - pct1;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm font-medium">
        <span>
          {team1Name} <span className="text-muted-foreground">{pct1}%</span>
        </span>
        <span>
          <span className="text-muted-foreground">{pct2}%</span> {team2Name}
        </span>
      </div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="bg-primary transition-all duration-300"
          style={{ width: `${pct1}%` }}
        />
        <div
          className="bg-muted-foreground/30 transition-all duration-300"
          style={{ width: `${pct2}%` }}
        />
      </div>
    </div>
  );
}
