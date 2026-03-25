"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { listTeams, type Team } from "@/lib/api";

interface TeamSearchProps {
  label: string;
  value: Team | null;
  onSelect: (team: Team) => void;
}

export function TeamSearch({ label, value, onSelect }: TeamSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [teams, setTeams] = useState<Team[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (query.length >= 2) {
        listTeams(query, 20)
          .then((r) => setTeams(r.items))
          .catch(() => {});
      } else {
        setTeams([]);
      }
    }, 200);
    return () => clearTimeout(timeout);
  }, [query]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <Input
        placeholder={value ? value.name : label}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        className="w-full"
      />
      {open && teams.length > 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover p-1 shadow-md">
          {teams.map((team) => (
            <button
              key={team.id}
              type="button"
              className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm hover:bg-muted cursor-pointer"
              onClick={() => {
                onSelect(team);
                setQuery("");
                setOpen(false);
              }}
            >
              <span>{team.name}</span>
              {team.current_elo && (
                <span className="text-xs text-muted-foreground">
                  {Math.round(team.current_elo)} Elo
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      {open && query.length >= 2 && teams.length === 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover p-3 text-center text-sm text-muted-foreground shadow-md">
          No teams found.
        </div>
      )}
    </div>
  );
}
