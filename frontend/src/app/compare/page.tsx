"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TeamSearch } from "@/components/team-search";
import { WinProbBar } from "@/components/win-prob-bar";
import { predict, type AdHocPrediction, type Team } from "@/lib/api";

export default function ComparePage() {
  const [team1, setTeam1] = useState<Team | null>(null);
  const [team2, setTeam2] = useState<Team | null>(null);
  const [result, setResult] = useState<AdHocPrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCompare() {
    if (!team1 || !team2) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await predict({ team1_id: team1.id, team2_id: team2.id });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

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

            {/* Key features */}
            <div>
              <h3 className="text-sm font-medium mb-2">Key Features</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                {Object.entries(result.features)
                  .filter(([k]) => k.includes("elo") || k.includes("diff") || k.includes("win_rate"))
                  .slice(0, 12)
                  .map(([key, val]) => (
                    <div key={key} className="rounded border px-2 py-1">
                      <span className="text-muted-foreground">{key}: </span>
                      <span className="font-mono">
                        {val != null ? (typeof val === "number" ? val.toFixed(3) : val) : "—"}
                      </span>
                    </div>
                  ))}
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Model: {result.model_version}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
