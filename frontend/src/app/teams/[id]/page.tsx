"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { getTeam, getTeamPlayers, type TeamProfile, type PlayerInfo } from "@/lib/api";

export default function TeamProfilePage() {
  const params = useParams();
  const router = useRouter();
  const teamId = Number(params.id);
  const [team, setTeam] = useState<TeamProfile | null>(null);
  const [players, setPlayers] = useState<PlayerInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!teamId) return;
    Promise.all([getTeam(teamId), getTeamPlayers(teamId)]).then(
      ([t, p]) => {
        setTeam(t);
        setPlayers(p.players);
        setLoading(false);
      }
    );
  }, [teamId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-[300px] w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!team) {
    return <p className="text-muted-foreground">Team not found.</p>;
  }

  // Downsample elo history for chart (take every Nth point)
  const eloData = team.elo_history;
  const step = Math.max(1, Math.floor(eloData.length / 200));
  const chartData = eloData
    .filter((_, i) => i % step === 0 || i === eloData.length - 1)
    .map((e) => ({
      date: new Date(e.date).toLocaleDateString(),
      elo: Math.round(e.elo),
    }));

  const currentRoster = players.filter((p) => p.is_current);
  const pastPlayers = players.filter((p) => !p.is_current);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{team.name}</h1>
        <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
          {team.current_elo && (
            <Badge variant="secondary">
              {Math.round(team.current_elo)} Elo
            </Badge>
          )}
          {team.first_seen && <span>Active since {team.first_seen}</span>}
        </div>
      </div>

      {/* Elo Chart */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Elo Rating Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  interval="preserveStartEnd"
                />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="elo"
                  stroke="#18181b"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Map Pool */}
      {team.map_pool.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Map Pool</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {team.map_pool.map((mp) => {
                const wr = Math.round(mp.win_rate * 100);
                const color =
                  wr >= 60
                    ? "text-green-600"
                    : wr >= 45
                    ? "text-foreground"
                    : "text-red-500";
                return (
                  <div
                    key={mp.map_name}
                    className="rounded-lg border p-3 text-center"
                  >
                    <p className="text-sm font-medium">{mp.map_name}</p>
                    <p className={`text-lg font-bold ${color}`}>{wr}%</p>
                    <p className="text-xs text-muted-foreground">
                      {mp.maps_played} maps
                    </p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Matches */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Matches</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Opponent</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Event</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {team.recent_matches.map((m) => {
                const won = m.winner_id === teamId;
                return (
                  <TableRow
                    key={m.match_id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => router.push(`/matches/${m.match_id}`)}
                  >
                    <TableCell className="text-xs">
                      {m.date
                        ? new Date(m.date).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/teams/${m.opponent_id}`}
                        className="hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {m.opponent_name}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {m.team1_score} - {m.team2_score}
                    </TableCell>
                    <TableCell>
                      <Badge variant={won ? "default" : "secondary"}>
                        {won ? "W" : "L"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {m.event}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Roster */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Roster</CardTitle>
        </CardHeader>
        <CardContent>
          {currentRoster.length > 0 && (
            <>
              <h3 className="text-sm font-medium mb-2">Current</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Player</TableHead>
                    <TableHead>Avg Rating</TableHead>
                    <TableHead>Maps</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {currentRoster.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium">{p.name}</TableCell>
                      <TableCell>
                        {p.avg_rating != null ? p.avg_rating.toFixed(2) : "—"}
                      </TableCell>
                      <TableCell>{p.appearances}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
          {pastPlayers.length > 0 && (
            <>
              <h3 className="text-sm font-medium mt-4 mb-2">Past Players</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Player</TableHead>
                    <TableHead>Avg Rating</TableHead>
                    <TableHead>Maps</TableHead>
                    <TableHead>Last Played</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pastPlayers.slice(0, 10).map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>{p.name}</TableCell>
                      <TableCell>
                        {p.avg_rating != null ? p.avg_rating.toFixed(2) : "—"}
                      </TableCell>
                      <TableCell>{p.appearances}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {p.last_played
                          ? new Date(p.last_played).toLocaleDateString()
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
