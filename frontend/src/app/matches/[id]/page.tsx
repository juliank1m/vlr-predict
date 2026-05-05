"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { WinProbBar } from "@/components/win-prob-bar";
import { getMatch, type MatchDetail } from "@/lib/api";
import { AgentIcon } from "@/components/agent-icon";
import { TeamLogo } from "@/components/team-logo";
import { getMapSplashUrl } from "@/lib/assets";

export default function MatchDetailPage() {
  const params = useParams();
  const matchId = Number(params.id);
  const [match, setMatch] = useState<MatchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("");

  useEffect(() => {
    if (!matchId) return;
    getMatch(matchId).then((m) => {
      setMatch(m);
      if (m.maps.length > 0) setActiveTab(String(m.maps[0].id));
      setLoading(false);
    });
  }, [matchId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!match) {
    return <p className="text-muted-foreground">Match not found.</p>;
  }

  // Get the active map's splash URL for the full-page background
  const activeMap = match.maps.find((m) => String(m.id) === activeTab);
  const bgUrl = activeMap ? getMapSplashUrl(activeMap.map_name) : null;

  return (
    <>
      {bgUrl && (
        <div
          className="fixed inset-0 z-0"
          style={{
            backgroundImage: `url(${bgUrl})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        >
          <div className="absolute inset-0 bg-background/55 backdrop-blur-[1px]" />
        </div>
      )}
      <div className="relative z-10 space-y-8 -mt-3">
      <div>
        <div className="flex items-center gap-5 text-3xl font-bold">
          <Link href={`/teams/${match.team1_id}`} className="flex items-center gap-3 hover:underline">
            <TeamLogo name={match.team1_name} size={64} />
            {match.team1_name}
          </Link>
          <span className="font-mono">
            {match.team1_score} - {match.team2_score}
          </span>
          <Link href={`/teams/${match.team2_id}`} className="flex items-center gap-3 hover:underline">
            {match.team2_name}
            <TeamLogo name={match.team2_name} size={64} />
          </Link>
        </div>
        <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
          <span>{match.event}</span>
          {match.stage && <span>/ {match.stage}</span>}
          {match.date && (
            <span>— {new Date(match.date).toLocaleDateString()}</span>
          )}
          {match.winner_name && (
            <Badge variant="default">{match.winner_name} wins</Badge>
          )}
        </div>
      </div>

      {match.predictions && match.predictions.length > 0 && (() => {
        const seriesPred = match.predictions.find((p) => p.map_name == null) ?? match.predictions[0];
        return (
          <Card >
            <CardHeader className="py-3">
              <CardTitle className="text-sm tracking-widest">Pre-Match Prediction</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <WinProbBar
                team1Name={match.team1_name}
                team2Name={match.team2_name}
                team1Prob={seriesPred.team1_win_prob}
              />
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Model: {seriesPred.model_version}</span>
                {seriesPred.correct === true && (
                  <Badge variant="default" className="bg-green-600">Correct</Badge>
                )}
                {seriesPred.correct === false && (
                  <Badge variant="secondary" className="bg-red-500 text-white">Incorrect</Badge>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })()}

      {match.odds && match.odds.length > 0 && (() => {
        const seriesPred = match.predictions?.find((p) => p.map_name == null) ?? match.predictions?.[0];
        const team1Prob = seriesPred?.team1_win_prob ?? null;
        const BOOKMAKER_LABELS: Record<string, string> = {
          ggbet: "GGBet",
          thunderpick: "Thunderpick",
          rainbet: "Rainbet",
          shuffle: "Shuffle",
          winz: "Winz",
        };
        const bookmakerLabel = (name: string) =>
          BOOKMAKER_LABELS[name.toLowerCase()] ??
          (name.length > 0 ? name[0].toUpperCase() + name.slice(1) : name);
        const formatRelative = (iso: string) => {
          if (!iso) return "—";
          const ts = new Date(iso).getTime();
          if (Number.isNaN(ts)) return "—";
          const diffSec = Math.floor((Date.now() - ts) / 1000);
          if (diffSec < 0) return "just now";
          if (diffSec < 60) return `${diffSec}s ago`;
          const diffMin = Math.floor(diffSec / 60);
          if (diffMin < 60) return `${diffMin} min ago`;
          const diffHr = Math.floor(diffMin / 60);
          if (diffHr < 24) return `${diffHr}h ago`;
          const diffDay = Math.floor(diffHr / 24);
          if (diffDay < 30) return `${diffDay}d ago`;
          return new Date(iso).toLocaleDateString();
        };
        const formatEv = (ev: number | null) => {
          if (ev == null || !Number.isFinite(ev)) return "—";
          const pct = Math.round(ev * 100);
          const sign = pct >= 0 ? "+" : "";
          return `${sign}${pct}%`;
        };
        return (
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm tracking-widest">Betting</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[160px]">Bookmaker</TableHead>
                    <TableHead className="text-center">{match.team1_name}</TableHead>
                    <TableHead className="text-center">{match.team2_name}</TableHead>
                    <TableHead className="text-center">{match.team1_name} Implied</TableHead>
                    <TableHead className="text-center">{match.team2_name} Implied</TableHead>
                    <TableHead className="text-center">{match.team1_name} EV</TableHead>
                    <TableHead className="text-center">{match.team2_name} EV</TableHead>
                    <TableHead className="text-right">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {match.odds.map((row) => {
                    const team1Implied = row.team1_decimal > 0 ? 1 / row.team1_decimal : null;
                    const team2Implied = row.team2_decimal > 0 ? 1 / row.team2_decimal : null;
                    const team1Ev =
                      team1Prob != null && team1Implied != null && team1Implied > 0
                        ? team1Prob / team1Implied - 1
                        : null;
                    const team2Ev =
                      team1Prob != null && team2Implied != null && team2Implied > 0
                        ? (1 - team1Prob) / team2Implied - 1
                        : null;
                    const evClass = (ev: number | null) =>
                      ev != null && ev > 0 ? "text-emerald-500" : "text-muted-foreground";
                    return (
                      <TableRow key={row.bookmaker}>
                        <TableCell className="font-medium">
                          {bookmakerLabel(row.bookmaker)}
                        </TableCell>
                        <TableCell className="text-center font-mono text-xs">
                          {row.team1_decimal.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-center font-mono text-xs">
                          {row.team2_decimal.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-center font-mono text-xs">
                          {team1Implied != null ? `${(team1Implied * 100).toFixed(1)}%` : "—"}
                        </TableCell>
                        <TableCell className="text-center font-mono text-xs">
                          {team2Implied != null ? `${(team2Implied * 100).toFixed(1)}%` : "—"}
                        </TableCell>
                        <TableCell className={`text-center font-mono text-xs ${evClass(team1Ev)}`}>
                          {formatEv(team1Ev)}
                        </TableCell>
                        <TableCell className={`text-center font-mono text-xs ${evClass(team2Ev)}`}>
                          {formatEv(team2Ev)}
                        </TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground">
                          {formatRelative(row.fetched_at)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        );
      })()}

      {match.maps.length > 0 && (
        <Tabs defaultValue={String(match.maps[0].id)} onValueChange={setActiveTab}>
          <TabsList>
            {match.maps.map((map) => (
              <TabsTrigger key={map.id} value={String(map.id)}>
                Map {map.map_number}: {map.map_name ?? "Unknown"}
                <span className="ml-1 font-mono text-xs">
                  ({map.team1_score}-{map.team2_score})
                </span>
              </TabsTrigger>
            ))}
          </TabsList>

          {match.maps.map((map) => {
            const team1Stats = map.player_stats.filter(
              (s) => s.team_id === match.team1_id
            );
            const team2Stats = map.player_stats.filter(
              (s) => s.team_id === match.team2_id
            );

            return (
              <TabsContent key={map.id} value={String(map.id)} className="space-y-4">
                <div className="flex items-center gap-3 text-sm">
                  <span className="font-medium">{map.map_name ?? "Unknown"}</span>
                  <span className="font-mono">
                    {map.team1_score} - {map.team2_score}
                  </span>
                  {map.winner_id && (
                    <Badge variant="secondary">
                      {map.winner_id === match.team1_id
                        ? match.team1_name
                        : match.team2_name}{" "}
                      wins
                    </Badge>
                  )}
                </div>

                {[
                  { name: match.team1_name, stats: team1Stats },
                  { name: match.team2_name, stats: team2Stats },
                ].map(({ name, stats }) => {
                  const mvpId = stats.length > 0
                    ? stats.reduce((best, s) => (s.rating ?? 0) > (best.rating ?? 0) ? s : best).player_id
                    : null;
                  return (
                  <Card key={name}>
                    <CardHeader className="py-1.5 px-4">
                      <CardTitle className="text-sm tracking-widest flex items-center gap-2">
                        <TeamLogo name={name} size={24} />
                        {name}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-[180px]">Player</TableHead>
                            <TableHead className="text-center">R</TableHead>
                            <TableHead className="text-center">ACS</TableHead>
                            <TableHead className="text-center">K</TableHead>
                            <TableHead className="text-center">D</TableHead>
                            <TableHead className="text-center">A</TableHead>
                            <TableHead className="text-center">+/−</TableHead>
                            <TableHead className="text-center">KAST</TableHead>
                            <TableHead className="text-center">ADR</TableHead>
                            <TableHead className="text-center">FK</TableHead>
                            <TableHead className="text-center">FD</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {stats.map((s) => {
                            const diff = s.kills - s.deaths;
                            return (
                            <TableRow key={s.player_id} className={s.player_id === mvpId ? "bg-amber-500/10" : ""}>
                              <TableCell>
                                <div className="flex items-center gap-2.5">
                                  <AgentIcon agentName={s.agent} size={32} />
                                  <div className="flex flex-col">
                                    <span className="font-semibold text-sm leading-tight">{s.player_name}</span>
                                    <span className="text-[0.65rem] text-muted-foreground leading-tight">{s.agent ?? ""}</span>
                                  </div>
                                </div>
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.rating?.toFixed(2) ?? "—"}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.acs?.toFixed(0) ?? "—"}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.kills}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.deaths}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.assists}
                              </TableCell>
                              <TableCell className={`text-center font-mono text-xs ${diff > 0 ? "text-green-500" : diff < 0 ? "text-red-400" : ""}`}>
                                {diff > 0 ? `+${diff}` : diff}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.kast != null ? `${s.kast.toFixed(0)}%` : "—"}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.adr?.toFixed(0) ?? "—"}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.first_kills}
                              </TableCell>
                              <TableCell className="text-center font-mono text-xs">
                                {s.first_deaths}
                              </TableCell>
                            </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                  );
                })}
              </TabsContent>
            );
          })}
        </Tabs>
      )}
      </div>
    </>
  );
}
