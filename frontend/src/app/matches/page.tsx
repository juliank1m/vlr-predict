"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Calendar, Search, ChevronLeft, ChevronRight } from "lucide-react";
import { TeamLogo } from "@/components/team-logo";
import { listMatches, type MatchSummary } from "@/lib/api";
import dynamic from "next/dynamic";

const AnimatedList = dynamic(() => import("@/../components/reactbits/AnimatedList"), { ssr: false }) as typeof import("@/../components/reactbits/AnimatedList").default;

function Pagination({ page, totalPages, setPage }: {
  page: number;
  totalPages: number;
  setPage: (p: number | ((prev: number) => number)) => void;
}) {
  const [jumpInput, setJumpInput] = useState(String(page));

  useEffect(() => { setJumpInput(String(page)); }, [page]);

  function handleJump(e: React.FormEvent) {
    e.preventDefault();
    const n = Math.max(1, Math.min(totalPages, Number(jumpInput) || 1));
    setPage(n);
  }

  return (
    <div className="flex items-center justify-center">
      <form onSubmit={handleJump} className="inline-flex items-center border border-border rounded overflow-hidden text-xs font-mono">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
          className="px-3 h-8 flex items-center gap-1 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-30 disabled:pointer-events-none border-r border-border"
        >
          <ChevronLeft size={13} />
          <span className="uppercase tracking-widest text-[0.65rem] font-semibold">Prev</span>
        </button>
        <div className="flex items-center h-8 px-2 gap-1">
          <input
            type="number"
            min={1}
            max={totalPages}
            value={jumpInput}
            onChange={(e) => setJumpInput(e.target.value)}
            className="w-10 h-6 rounded border border-border bg-muted/50 text-center text-xs font-mono text-foreground outline-none focus:border-primary focus:bg-muted [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
          <span className="text-muted-foreground">/ {totalPages}</span>
        </div>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
          className="px-3 h-8 flex items-center gap-1 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-30 disabled:pointer-events-none border-l border-border"
        >
          <span className="uppercase tracking-widest text-[0.65rem] font-semibold">Next</span>
          <ChevronRight size={13} />
        </button>
      </form>
    </div>
  );
}

export default function MatchesPage() {
  return (
    <Suspense fallback={<div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>}>
      <MatchesContent />
    </Suspense>
  );
}

function MatchesContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState(searchParams.get("search") ?? "");
  const pageSize = 25;

  const page = Number(searchParams.get("page") ?? "1");
  const search = searchParams.get("search") ?? "";

  function updateParams(newPage: number, newSearch: string) {
    const params = new URLSearchParams();
    if (newPage > 1) params.set("page", String(newPage));
    if (newSearch) params.set("search", newSearch);
    const qs = params.toString();
    router.push(`/matches${qs ? `?${qs}` : ""}`);
  }

  const setPage = (p: number | ((prev: number) => number)) => {
    const next = typeof p === "function" ? p(page) : p;
    updateParams(next, search);
  };

  const fetchMatches = useCallback(() => {
    setLoading(true);
    listMatches(page, pageSize, search || undefined).then((r) => {
      setMatches(r.items);
      setTotal(r.total);
      setLoading(false);
    });
  }, [page, search]);

  useEffect(() => {
    fetchMatches();
  }, [fetchMatches]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    updateParams(1, searchInput);
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-widest">Matches</h1>
          <p className="text-sm text-muted-foreground">
            {total.toLocaleString()} matches{search ? ` matching "${search}"` : " in database"}
          </p>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search teams or events..."
              className="h-9 w-64 rounded border border-border bg-secondary pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <Button type="submit" size="sm" variant="default">
            Search
          </Button>
          {search && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => { setSearchInput(""); updateParams(1, ""); }}
            >
              Clear
            </Button>
          )}
        </form>
      </div>

      {totalPages > 1 && <Pagination page={page} totalPages={totalPages} setPage={setPage} />}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : matches.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No matches found{search ? ` for "${search}"` : ""}.
          </CardContent>
        </Card>
      ) : (
        <AnimatedList
          items={matches}
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
                      m.winner_id === m.team1_id
                        ? "font-bold"
                        : "text-muted-foreground"
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
                      m.winner_id === m.team2_id
                        ? "font-bold"
                        : "text-muted-foreground"
                    }`}
                  >
                    {m.team2_name}
                    <TeamLogo name={m.team2_name} size={22} />
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
                  <span className="w-14 text-center">
                    {m.map_count > 0 && (
                      <Badge variant="secondary">{m.map_count} map{m.map_count !== 1 ? "s" : ""}</Badge>
                    )}
                  </span>
                  <span className="hidden sm:inline w-44 truncate">{m.event}</span>
                  {m.date && (
                    <span className="flex items-center gap-1 shrink-0">
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

      {totalPages > 1 && <Pagination page={page} totalPages={totalPages} setPage={setPage} />}
    </div>
  );
}
