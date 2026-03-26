"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Calendar } from "lucide-react";
import { listMatches, type MatchSummary } from "@/lib/api";

export default function MatchesPage() {
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const pageSize = 25;

  useEffect(() => {
    setLoading(true);
    listMatches(page, pageSize).then((r) => {
      setMatches(r.items);
      setTotal(r.total);
      setLoading(false);
    });
  }, [page]);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Matches</h1>
        <p className="text-muted-foreground">
          {total.toLocaleString()} matches in database
        </p>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {matches.map((m) => (
            <Link key={m.id} href={`/matches/${m.id}`} className="block">
              <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                <CardContent className="flex items-center justify-between py-3 px-4">
                  <div className="flex items-center gap-3 text-sm">
                    <span
                      className={
                        m.winner_id === m.team1_id
                          ? "font-bold"
                          : "text-muted-foreground"
                      }
                    >
                      {m.team1_name}
                    </span>
                    <span className="font-mono text-xs">
                      {m.team1_score} - {m.team2_score}
                    </span>
                    <span
                      className={
                        m.winner_id === m.team2_id
                          ? "font-bold"
                          : "text-muted-foreground"
                      }
                    >
                      {m.team2_name}
                    </span>
                    <Badge variant="secondary" className="text-xs">
                      Bo{m.map_count}
                    </Badge>
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
            </Link>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
