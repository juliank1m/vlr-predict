"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { TeamSearch } from "@/components/team-search";
import { WinProbBar } from "@/components/win-prob-bar";
import {
  getUpcomingPredictions,
  listMatches,
  predict,
  type AdHocPrediction,
  type PredictionItem,
  type MatchSummary,
  type Team,
} from "@/lib/api";

export default function HomePage() {
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [recentMatches, setRecentMatches] = useState<MatchSummary[]>([]);
  const [loading, setLoading] = useState(true);

  // ad-hoc prediction state
  const [team1, setTeam1] = useState<Team | null>(null);
  const [team2, setTeam2] = useState<Team | null>(null);
  const [adhocResult, setAdhocResult] = useState<AdHocPrediction | null>(null);
  const [predicting, setPredicting] = useState(false);

  useEffect(() => {
    Promise.all([
      getUpcomingPredictions(25).catch(() => ({ items: [] })),
      listMatches(1, 10).catch(() => ({ items: [] })),
    ]).then(([preds, matches]) => {
      setPredictions(preds.items);
      setRecentMatches(matches.items);
      setLoading(false);
    });
  }, []);

  async function handlePredict() {
    if (!team1 || !team2) return;
    setPredicting(true);
    setAdhocResult(null);
    try {
      const result = await predict({ team1_id: team1.id, team2_id: team2.id });
      setAdhocResult(result);
    } catch {
      // ignore
    } finally {
      setPredicting(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Predictions</h1>
        <p className="text-muted-foreground">
          Model-powered win probabilities for pro Valorant matches.
        </p>
      </div>

      {/* Ad-hoc prediction */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Quick Prediction</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr]">
            <TeamSearch label="Select Team 1..." value={team1} onSelect={setTeam1} />
            <span className="hidden sm:flex items-center text-sm text-muted-foreground font-medium">
              vs
            </span>
            <TeamSearch label="Select Team 2..." value={team2} onSelect={setTeam2} />
          </div>
          <button
            onClick={handlePredict}
            disabled={!team1 || !team2 || predicting}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
          >
            {predicting ? "Predicting..." : "Predict"}
          </button>
          {adhocResult && (
            <div className="pt-2">
              <WinProbBar
                team1Name={adhocResult.team1.name}
                team2Name={adhocResult.team2.name}
                team1Prob={adhocResult.team1_win_prob}
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Model: {adhocResult.model_version}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upcoming predictions */}
      {predictions.length > 0 && (
        <>
          <h2 className="text-lg font-semibold">Upcoming</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {predictions.map((p) => (
              <Card key={p.id}>
                <CardContent className="pt-6 space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <Link
                      href={`/teams/${p.team1_id}`}
                      className="font-medium hover:underline"
                    >
                      {p.team1_name}
                    </Link>
                    {p.map_name && <Badge variant="secondary">{p.map_name}</Badge>}
                    <Link
                      href={`/teams/${p.team2_id}`}
                      className="font-medium hover:underline"
                    >
                      {p.team2_name}
                    </Link>
                  </div>
                  <WinProbBar
                    team1Name={p.team1_name}
                    team2Name={p.team2_name}
                    team1Prob={p.team1_win_prob}
                  />
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      <Separator />

      {/* Recent matches */}
      <h2 className="text-lg font-semibold">Recent Matches</h2>
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {recentMatches.map((m) => (
            <Link key={m.id} href={`/matches/${m.id}`}>
              <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                <CardContent className="flex items-center justify-between py-3 px-4">
                  <div className="flex items-center gap-3 text-sm">
                    <span
                      className={
                        m.winner_id === m.team1_id ? "font-bold" : "text-muted-foreground"
                      }
                    >
                      {m.team1_name}
                    </span>
                    <span className="font-mono text-xs">
                      {m.team1_score} - {m.team2_score}
                    </span>
                    <span
                      className={
                        m.winner_id === m.team2_id ? "font-bold" : "text-muted-foreground"
                      }
                    >
                      {m.team2_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{m.event}</span>
                    {m.date && (
                      <span>{new Date(m.date).toLocaleDateString()}</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
