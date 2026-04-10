"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AccentSeparator } from "@/components/accent-separator";
import { Zap, Trophy, Calendar, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";

const AnimatedList = dynamic(() => import("@/../components/reactbits/AnimatedList"), { ssr: false }) as typeof import("@/../components/reactbits/AnimatedList").default;
import { TeamSearch } from "@/components/team-search";
import { TeamLogo } from "@/components/team-logo";
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
import { getAllMapSplashUrls } from "@/lib/assets";

export default function HomePage() {
  const router = useRouter();
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [recentMatches, setRecentMatches] = useState<MatchSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"date" | "confidence">("date");
  const [heroUrl, setHeroUrl] = useState<string | null>(null);

  // ad-hoc prediction state
  const [team1, setTeam1] = useState<Team | null>(null);
  const [team2, setTeam2] = useState<Team | null>(null);
  const [adhocResult, setAdhocResult] = useState<AdHocPrediction | null>(null);
  const [predicting, setPredicting] = useState(false);

  useEffect(() => {
    const urls = getAllMapSplashUrls();
    setHeroUrl(urls[Math.floor(Math.random() * urls.length)]);

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
      {/* Hero section */}
      <div className="relative rounded-sm border border-border/30">
        {heroUrl && (
          <div
            className="absolute inset-0 overflow-hidden rounded-sm"
            style={{
              backgroundImage: `url(${heroUrl})`,
              backgroundSize: "cover",
              backgroundPosition: "center 30%",
            }}
          >
            <div className="absolute inset-0 bg-gradient-to-b from-background/60 via-background/70 to-background" />
          </div>
        )}
        <div className="relative z-10 px-6 pt-10 pb-8 space-y-6">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold tracking-widest">
              Val<span className="text-primary">/</span>Predict
            </h1>
            <p className="text-sm text-muted-foreground tracking-wide mt-1">
              Model-powered win probabilities for pro Valorant matches.
            </p>
          </div>

          {/* Quick prediction inline in hero */}
          <div className="max-w-2xl space-y-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">Quick Prediction</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto_1fr]">
              <TeamSearch label="Team 1..." value={team1} onSelect={setTeam1} />
              <span className="hidden sm:flex items-center text-xs text-muted-foreground font-bold uppercase tracking-widest">
                vs
              </span>
              <TeamSearch label="Team 2..." value={team2} onSelect={setTeam2} />
            </div>
            <button
              onClick={handlePredict}
              disabled={!team1 || !team2 || predicting}
              className="inline-flex items-center gap-2 bg-primary px-6 py-2.5 text-xs font-bold uppercase tracking-widest text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
            >
              {predicting ? "Predicting..." : "Predict"}
              {!predicting && <ArrowRight size={14} />}
            </button>
            {adhocResult && (
              <div className="pt-1">
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
          </div>
        </div>
      </div>

      {/* Upcoming predictions */}
      {predictions.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Zap size={16} className="text-primary" />
              Upcoming
            </h2>
            <div className="flex gap-1 text-xs">
              <button
                onClick={() => setSortBy("date")}
                className={`rounded px-2 py-1 transition-colors ${sortBy === "date" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}
              >
                By Date
              </button>
              <button
                onClick={() => setSortBy("confidence")}
                className={`rounded px-2 py-1 transition-colors ${sortBy === "confidence" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}
              >
                By Confidence
              </button>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {[...predictions]
              .sort((a, b) =>
                sortBy === "confidence"
                  ? Math.max(b.team1_win_prob, b.team2_win_prob) - Math.max(a.team1_win_prob, a.team2_win_prob)
                  : 0
              )
              .map((p) => (
              <Card key={p.id}>
                <CardContent className="pt-6 space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <Link
                      href={`/teams/${p.team1_id}`}
                      className="flex items-center gap-2 font-medium hover:underline"
                    >
                      <TeamLogo name={p.team1_name} size={22} />
                      {p.team1_name}
                    </Link>
                    {p.map_name && <Badge variant="secondary">{p.map_name}</Badge>}
                    <Link
                      href={`/teams/${p.team2_id}`}
                      className="flex items-center gap-2 font-medium hover:underline"
                    >
                      {p.team2_name}
                      <TeamLogo name={p.team2_name} size={22} />
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

      <AccentSeparator />

      {/* Recent matches */}
      <h2 className="text-lg font-semibold flex items-center gap-2">
        <Trophy size={16} className="text-primary" />
        Recent Matches
      </h2>
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <AnimatedList
          items={recentMatches}
          showGradients={false}
          enableArrowNavigation={false}
          displayScrollbar={false}
          onItemSelect={(m) => { router.push(`/matches/${m.id}`); }}
          renderItem={(m, _index, isSelected) => (
            <Card className={`transition-colors ${isSelected ? "border-l-primary/50 bg-card/90" : ""}`}>
              <CardContent className="flex items-center justify-between py-3 px-4">
                <div className="flex items-center gap-3 text-sm">
                  <span
                    className={`flex items-center gap-1.5 ${
                      m.winner_id === m.team1_id ? "font-bold" : "text-muted-foreground"
                    }`}
                  >
                    <TeamLogo name={m.team1_name} size={22} />
                    {m.team1_name}
                  </span>
                  <span className="font-mono text-xs px-2 py-0.5 bg-muted/50 rounded">
                    {m.team1_score} - {m.team2_score}
                  </span>
                  <span
                    className={`flex items-center gap-1.5 ${
                      m.winner_id === m.team2_id ? "font-bold" : "text-muted-foreground"
                    }`}
                  >
                    {m.team2_name}
                    <TeamLogo name={m.team2_name} size={22} />
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="hidden sm:inline">{m.event}</span>
                  {m.date && (
                    <span className="flex items-center gap-1">
                      <Calendar size={12} />
                      {new Date(m.date).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        />
      )}
    </div>
  );
}
