"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Lock, Loader2, CheckCircle, XCircle, Database, Brain, RefreshCw, Terminal, ListChecks, Square } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type JobStatus = "idle" | "running" | "completed" | "failed";

interface JobState {
  status: JobStatus;
  result?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string;
  completed_at?: string;
}

const initialJob: JobState = { status: "idle" };

export default function AdminPage() {
  const [password, setPassword] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [authError, setAuthError] = useState(false);

  const [scrapeJob, setScrapeJob] = useState<JobState>(initialJob);
  const [eloJob, setEloJob] = useState<JobState>(initialJob);
  const [retrainJob, setRetrainJob] = useState<JobState>(initialJob);
  const [vetoJob, setVetoJob] = useState<JobState>(initialJob);
  const [roundsJob, setRoundsJob] = useState<JobState>(initialJob);
  const [tuneJob, setTuneJob] = useState<JobState>(initialJob);
  const [scrapePages, setScrapePages] = useState(5);

  const [logs, setLogs] = useState<Record<string, string[]>>({});
  const [activeLog, setActiveLog] = useState<string | null>(null);
  const logCountRef = useRef<Record<string, number>>({});
  const terminalRef = useRef<HTMLDivElement>(null);

  const authHeader = useCallback(
    () => ({ Authorization: "Basic " + btoa("admin:" + password) }),
    [password]
  );

  // Poll logs only for the active/visible job
  useEffect(() => {
    if (!activeLog || !authenticated) return;
    const jobState = { scrape: scrapeJob, elo: eloJob, retrain: retrainJob, backfill_veto: vetoJob, backfill_rounds: roundsJob, tune: tuneJob }[activeLog];
    if (!jobState || jobState.status !== "running") return;

    const poll = async () => {
      const since = logCountRef.current[activeLog] ?? 0;
      try {
        const res = await fetch(
          `${API_BASE}/api/admin/logs/${activeLog}?since=${since}`,
          { headers: authHeader() }
        );
        if (!res.ok) return;
        const data = await res.json();
        if (data.lines.length > 0) {
          setLogs((prev) => {
            const combined = [...(prev[activeLog] ?? []), ...data.lines];
            return {
              ...prev,
              [activeLog]: combined.slice(-500),
            };
          });
          logCountRef.current[activeLog] = data.total;
        }
      } catch {
        // ignore
      }
    };

    poll(); // fetch immediately
    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [activeLog, scrapeJob.status, eloJob.status, retrainJob.status, vetoJob.status, roundsJob.status, tuneJob.status, authenticated, authHeader]);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs, activeLog]);

  const handleLogin = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/status`, {
        headers: authHeader(),
      });
      if (res.ok) {
        setAuthenticated(true);
        setAuthError(false);
        const data = await res.json();
        if (data.scrape) setScrapeJob(data.scrape);
        if (data.elo) setEloJob(data.elo);
        if (data.retrain) setRetrainJob(data.retrain);
        if (data.backfill_veto) setVetoJob(data.backfill_veto);
        if (data.backfill_rounds) setRoundsJob(data.backfill_rounds);
        if (data.tune) setTuneJob(data.tune);
      } else {
        setAuthError(true);
      }
    } catch {
      setAuthError(true);
    }
  };

  const triggerJob = async (
    endpoint: string,
    jobId: string,
    setJob: (j: JobState) => void
  ) => {
    setJob({ status: "running" });
    // Clear previous logs
    setLogs((prev) => ({ ...prev, [jobId]: [] }));
    logCountRef.current[jobId] = 0;
    setActiveLog(jobId);
    try {
      const res = await fetch(`${API_BASE}/api/admin/${endpoint}`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJob(data);
      pollJob();
    } catch (e) {
      setJob({ status: "failed", error: String(e) });
    }
  };

  const stopJob = async (jobId: string) => {
    try {
      await fetch(`${API_BASE}/api/admin/stop/${jobId}`, {
        method: "POST",
        headers: authHeader(),
      });
    } catch {
      // ignore
    }
  };

  const pollJob = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/admin/status`, {
          headers: authHeader(),
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.scrape) setScrapeJob(data.scrape);
        if (data.elo) setEloJob(data.elo);
        if (data.retrain) setRetrainJob(data.retrain);
        if (data.backfill_veto) setVetoJob(data.backfill_veto);
        if (data.backfill_rounds) setRoundsJob(data.backfill_rounds);
        if (data.tune) setTuneJob(data.tune);
        const anyRunning = Object.values(data).some(
          (j: unknown) => (j as JobState).status === "running"
        );
        if (!anyRunning) clearInterval(interval);
      } catch {
        clearInterval(interval);
      }
    }, 2000);
  }, [authHeader]);

  if (!authenticated) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Card className="w-80">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Lock size={18} />
              Admin Panel
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              className="w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
            />
            {authError && (
              <p className="text-sm text-red-400">Invalid password</p>
            )}
            <Button onClick={handleLogin} className="w-full">
              Login
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const jobs = [
    {
      id: "scrape",
      label: "Scrape Matches",
      description: "Fetch recent results from VLR",
      icon: RefreshCw,
      state: scrapeJob,
      action: () => triggerJob(`scrape?pages=${scrapePages}`, "scrape", setScrapeJob),
      extra: (
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Pages:</label>
          <input
            type="number"
            min={1}
            max={100}
            value={scrapePages}
            onChange={(e) => setScrapePages(Number(e.target.value))}
            className="w-16 rounded border border-border bg-background px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      ),
    },
    {
      id: "elo",
      label: "Recompute Elo",
      description: "Recalculate all team Elo ratings",
      icon: Database,
      state: eloJob,
      action: () => triggerJob("elo", "elo", setEloJob),
    },
    {
      id: "retrain",
      label: "Retrain Model",
      description: "Train prediction model on all data",
      icon: Brain,
      state: retrainJob,
      action: () => triggerJob("retrain", "retrain", setRetrainJob),
    },
    {
      id: "tune",
      label: "Tune Model",
      description: "Test hyperparameter configs and retrain with best",
      icon: Brain,
      state: tuneJob,
      action: () => triggerJob("tune", "tune", setTuneJob),
    },
    {
      id: "backfill_veto",
      label: "Backfill Veto",
      description: "Re-scrape matches to extract veto data",
      icon: ListChecks,
      state: vetoJob,
      action: () => triggerJob("backfill-veto", "backfill_veto", setVetoJob),
    },
    {
      id: "backfill_rounds",
      label: "Backfill Rounds",
      description: "Scrape round-by-round data for all matches",
      icon: ListChecks,
      state: roundsJob,
      action: () => triggerJob("backfill-rounds", "backfill_rounds", setRoundsJob),
    },
  ];

  const activeLogLines = activeLog ? (logs[activeLog] ?? []) : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Admin Panel</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {jobs.map((job) => (
          <Card key={job.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <job.icon size={16} />
                {job.label}
              </CardTitle>
              <p className="text-xs text-muted-foreground">{job.description}</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {"extra" in job && job.extra}
              <StatusBadge state={job.state} />
              {job.state.result && (
                <pre className="text-xs bg-muted/50 rounded p-2 overflow-auto max-h-24">
                  {JSON.stringify(job.state.result, null, 2)}
                </pre>
              )}
              {job.state.error && (
                <p className="text-xs text-red-400 break-all">{job.state.error}</p>
              )}
              <div className="flex gap-2">
                {job.state.status === "running" ? (
                  <Button
                    onClick={() => stopJob(job.id)}
                    className="flex-1"
                    variant="destructive"
                  >
                    <Square size={14} className="mr-1" />
                    Stop
                  </Button>
                ) : (
                  <Button
                    onClick={job.action}
                    className="flex-1"
                  >
                    Run
                  </Button>
                )}
                {(logs[job.id]?.length ?? 0) > 0 && (
                  <Button
                    variant={activeLog === job.id ? "default" : "outline"}
                    size="icon"
                    onClick={() => setActiveLog(activeLog === job.id ? null : job.id)}
                    title="View logs"
                  >
                    <Terminal size={14} />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Terminal log viewer */}
      {activeLog && (
        <Card className="border-border/50">
          <CardHeader className="py-2 px-4">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-sm font-mono">
                <Terminal size={14} />
                {activeLog} logs
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-6"
                onClick={() => setActiveLog(null)}
              >
                Close
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div
              ref={terminalRef}
              className="bg-black/80 rounded-b-lg p-3 font-mono text-xs leading-5 overflow-auto max-h-80 min-h-[120px]"
            >
              {activeLogLines.length === 0 ? (
                <span className="text-muted-foreground">Waiting for output...</span>
              ) : (
                activeLogLines.map((line, i) => (
                  <div
                    key={i}
                    className={
                      line.includes("ERROR")
                        ? "text-red-300"
                        : line.includes("WARNING")
                          ? "text-yellow-300"
                          : "text-rose-300"
                    }
                  >
                    {line}
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatusBadge({ state }: { state: JobState }) {
  if (state.status === "idle") return null;
  const variants: Record<string, { variant: "default" | "secondary" | "destructive"; icon: typeof CheckCircle }> = {
    running: { variant: "secondary", icon: Loader2 },
    completed: { variant: "default", icon: CheckCircle },
    failed: { variant: "destructive", icon: XCircle },
  };
  const v = variants[state.status];
  if (!v) return null;
  return (
    <Badge variant={v.variant} className="gap-1">
      <v.icon size={12} className={state.status === "running" ? "animate-spin" : ""} />
      {state.status}
      {state.completed_at && (
        <span className="ml-1 opacity-70">
          {new Date(state.completed_at).toLocaleTimeString()}
        </span>
      )}
    </Badge>
  );
}
