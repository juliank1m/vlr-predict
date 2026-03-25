"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TeamSearch } from "@/components/team-search";
import { WinProbBar } from "@/components/win-prob-bar";
import {
  predict,
  getTeam,
  type AdHocPrediction,
  type Team,
  type TeamProfile,
} from "@/lib/api";

export default function ComparePage() {
  const [team1, setTeam1] = useState<Team | null>(null);
  const [team2, setTeam2] = useState<Team | null>(null);
  const [result, setResult] = useState<AdHocPrediction | null>(null);
  const [profile1, setProfile1] = useState<TeamProfile | null>(null);
  const [profile2, setProfile2] = useState<TeamProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCompare() {
    if (!team1 || !team2) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setProfile1(null);
    setProfile2(null);
    try {
      const [r, p1, p2] = await Promise.all([
        predict({ team1_id: team1.id, team2_id: team2.id }),
        getTeam(team1.id),
        getTeam(team2.id),
      ]);
      setResult(r);
      setProfile1(p1);
      setProfile2(p2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  // H2H record from recent matches
  const h2hMatches = profile1
    ? profile1.recent_matches.filter(
        (m) => m.opponent_id === team2?.id
      )
    : [];
  const h2hWins = h2hMatches.filter((m) => m.winner_id === team1?.id).length;
  const h2hLosses = h2hMatches.filter((m) => m.winner_id === team2?.id).length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Head-to-Head</h1>
        <p className="text-muted-foreground">
          Compare two teams and get a model prediction.
        </p>
      </div>

      <Card className="overflow-visible">
        <CardContent className="pt-6 space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr]">
            <div className="space-y-2">
              <label className="text-sm font-medium">Team 1</label>
              <TeamSearch label="Select team..." value={team1} onSelect={setTeam1} />
              {team1 && (
                <div className="text-xs text-muted-foreground">
                  <Link href={`/teams/${team1.id}`} className="hover:underline">
                    View profile
                  </Link>
                  {team1.current_elo && (
                    <span className="ml-2">{Math.round(team1.current_elo)} Elo</span>
                  )}
                </div>
              )}
            </div>
            <span className="hidden sm:flex items-center text-lg font-bold text-muted-foreground">
              vs
            </span>
            <div className="space-y-2">
              <label className="text-sm font-medium">Team 2</label>
              <TeamSearch label="Select team..." value={team2} onSelect={setTeam2} />
              {team2 && (
                <div className="text-xs text-muted-foreground">
                  <Link href={`/teams/${team2.id}`} className="hover:underline">
                    View profile
                  </Link>
                  {team2.current_elo && (
                    <span className="ml-2">{Math.round(team2.current_elo)} Elo</span>
                  )}
                </div>
              )}
            </div>
          </div>

          <button
            onClick={handleCompare}
            disabled={!team1 || !team2 || loading}
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
          >
            {loading ? "Predicting..." : "Compare"}
          </button>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Prediction Result</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <WinProbBar
              team1Name={result.team1.name}
              team2Name={result.team2.name}
              team1Prob={result.team1_win_prob}
            />

            <div className="grid grid-cols-2 gap-4 text-center">
              <div className="rounded-lg border p-4">
                <p className="text-2xl font-bold">
                  {Math.round(result.team1_win_prob * 100)}%
                </p>
                <p className="text-sm text-muted-foreground">{result.team1.name}</p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-2xl font-bold">
                  {Math.round(result.team2_win_prob * 100)}%
                </p>
                <p className="text-sm text-muted-foreground">{result.team2.name}</p>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Model: {result.model_version}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Side-by-side stats */}
      {profile1 && profile2 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Side-by-Side Comparison</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right w-1/3">{profile1.name}</TableHead>
                  <TableHead className="text-center">Stat</TableHead>
                  <TableHead className="w-1/3">{profile2.name}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="text-right font-mono">
                    {profile1.current_elo ? Math.round(profile1.current_elo) : "—"}
                  </TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground">Elo Rating</TableCell>
                  <TableCell className="font-mono">
                    {profile2.current_elo ? Math.round(profile2.current_elo) : "—"}
                  </TableCell>
                </TableRow>
                {(() => {
                  const wr1 = profile1.recent_matches.length > 0
                    ? profile1.recent_matches.filter((m) => m.winner_id === profile1.id).length / profile1.recent_matches.length
                    : null;
                  const wr2 = profile2.recent_matches.length > 0
                    ? profile2.recent_matches.filter((m) => m.winner_id === profile2.id).length / profile2.recent_matches.length
                    : null;
                  return (
                    <TableRow>
                      <TableCell className="text-right font-mono">
                        {wr1 != null ? `${(wr1 * 100).toFixed(0)}%` : "—"}
                      </TableCell>
                      <TableCell className="text-center text-xs text-muted-foreground">Recent Win Rate</TableCell>
                      <TableCell className="font-mono">
                        {wr2 != null ? `${(wr2 * 100).toFixed(0)}%` : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })()}
                <TableRow>
                  <TableCell className="text-right font-mono">
                    {profile1.recent_matches.length}
                  </TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground">Recent Maps</TableCell>
                  <TableCell className="font-mono">
                    {profile2.recent_matches.length}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-right font-mono">
                    {profile1.map_pool.length}
                  </TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground">Maps in Pool</TableCell>
                  <TableCell className="font-mono">
                    {profile2.map_pool.length}
                  </TableCell>
                </TableRow>
                {/* Map-by-map comparison */}
                {(() => {
                  const allMaps = [...new Set([
                    ...profile1.map_pool.map((m) => m.map_name),
                    ...profile2.map_pool.map((m) => m.map_name),
                  ])].sort();
                  return allMaps.map((mapName) => {
                    const m1 = profile1.map_pool.find((m) => m.map_name === mapName);
                    const m2 = profile2.map_pool.find((m) => m.map_name === mapName);
                    return (
                      <TableRow key={mapName}>
                        <TableCell className="text-right font-mono text-xs">
                          {m1 ? `${(m1.win_rate * 100).toFixed(0)}% (${m1.maps_played})` : "—"}
                        </TableCell>
                        <TableCell className="text-center text-xs text-muted-foreground">
                          {mapName}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {m2 ? `${(m2.win_rate * 100).toFixed(0)}% (${m2.maps_played})` : "—"}
                        </TableCell>
                      </TableRow>
                    );
                  });
                })()}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* H2H record */}
      {profile1 && profile2 && h2hMatches.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Head-to-Head Record: {profile1.name} {h2hWins}-{h2hLosses} {profile2.name}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {h2hMatches.map((m) => (
              <div
                key={m.match_id}
                className="flex items-center justify-between text-sm rounded border px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className={m.winner_id === team1?.id ? "font-bold" : "text-muted-foreground"}>
                    {profile1.name}
                  </span>
                  <span className="font-mono text-xs">
                    {m.team1_score} - {m.team2_score}
                  </span>
                  <span className={m.winner_id === team2?.id ? "font-bold" : "text-muted-foreground"}>
                    {profile2.name}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {m.event} — {new Date(m.date).toLocaleDateString()}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
