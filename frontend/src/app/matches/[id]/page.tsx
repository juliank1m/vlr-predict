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

  useEffect(() => {
    if (!matchId) return;
    getMatch(matchId).then((m) => {
      setMatch(m);
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 text-2xl font-bold">
          <Link href={`/teams/${match.team1_id}`} className="flex items-center gap-2 hover:underline">
            <TeamLogo name={match.team1_name} size={28} />
            {match.team1_name}
          </Link>
          <span className="font-mono">
            {match.team1_score} - {match.team2_score}
          </span>
          <Link href={`/teams/${match.team2_id}`} className="flex items-center gap-2 hover:underline">
            {match.team2_name}
            <TeamLogo name={match.team2_name} size={28} />
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

      {/* Pre-match prediction */}
      {match.predictions && match.predictions.length > 0 && (() => {
        const seriesPred = match.predictions.find((p) => p.map_name == null) ?? match.predictions[0];
        return (
          <Card className="border-t-2 border-t-primary">
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

      {/* Maps */}
      {match.maps.length > 0 && (
        <Tabs defaultValue={String(match.maps[0].id)}>
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
              <TabsContent key={map.id} value={String(map.id)}>
                <div
                  className="relative rounded-lg overflow-hidden"
                  style={{
                    backgroundImage: getMapSplashUrl(map.map_name)
                      ? `url(${getMapSplashUrl(map.map_name)})`
                      : undefined,
                    backgroundSize: "cover",
                    backgroundPosition: "center",
                  }}
                >
                  <div className="bg-background/90 backdrop-blur-sm p-4 space-y-4 rounded-lg">
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
                    <CardHeader className="py-3">
                      <CardTitle className="text-sm tracking-widest">{name}</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Player</TableHead>
                            <TableHead>Agent</TableHead>
                            <TableHead className="text-right">Rating</TableHead>
                            <TableHead className="text-right">ACS</TableHead>
                            <TableHead className="text-right">K</TableHead>
                            <TableHead className="text-right">D</TableHead>
                            <TableHead className="text-right">A</TableHead>
                            <TableHead className="text-right">KAST</TableHead>
                            <TableHead className="text-right">ADR</TableHead>
                            <TableHead className="text-right">FK</TableHead>
                            <TableHead className="text-right">FD</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {stats.map((s) => (
                            <TableRow key={s.player_id} className={s.player_id === mvpId ? "bg-amber-500/10" : ""}>
                              <TableCell className="font-medium">
                                {s.player_name}
                              </TableCell>
                              <TableCell className="text-xs">
                                <span className="flex items-center gap-1.5">
                                  <AgentIcon agentName={s.agent} size={18} />
                                  {s.agent}
                                </span>
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.rating?.toFixed(2) ?? "—"}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.acs?.toFixed(0) ?? "—"}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs text-green-500/80">
                                {s.kills}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs text-red-400/80">
                                {s.deaths}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.assists}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.kast != null ? `${s.kast.toFixed(0)}%` : "—"}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.adr?.toFixed(0) ?? "—"}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.first_kills}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {s.first_deaths}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                  );
                })}
                  </div>
                </div>
              </TabsContent>
            );
          })}
        </Tabs>
      )}
    </div>
  );
}
