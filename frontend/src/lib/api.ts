const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchAPI<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// --- Types ---

export interface Team {
  id: number;
  name: string;
  first_seen: string | null;
  current_elo: number | null;
}

export interface EloPoint {
  date: string;
  map_id: number;
  map_name: string;
  elo: number;
  elo_delta: number;
}

export interface RecentMatch {
  match_id: number;
  date: string;
  opponent_id: number;
  opponent_name: string;
  team1_score: number;
  team2_score: number;
  winner_id: number | null;
  event: string;
  stage: string;
}

export interface MapPoolEntry {
  map_name: string;
  maps_played: number;
  win_rate: number;
}

export interface TeamProfile extends Team {
  elo_history: EloPoint[];
  recent_matches: RecentMatch[];
  map_pool: MapPoolEntry[];
}

export interface PlayerInfo {
  id: number;
  name: string;
  url: string | null;
  appearances: number;
  last_played: string | null;
  avg_rating: number | null;
  is_current: boolean;
}

export interface MatchSummary {
  id: number;
  date: string;
  team1_id: number;
  team1_name: string;
  team2_id: number;
  team2_name: string;
  team1_score: number;
  team2_score: number;
  winner_id: number | null;
  winner_name: string | null;
  event: string;
  stage: string;
  url: string | null;
  map_count: number;
}

export interface PlayerStat {
  team_id: number;
  player_id: number;
  player_name: string;
  agent: string;
  rating: number | null;
  acs: number | null;
  kills: number;
  deaths: number;
  assists: number;
  kast: number | null;
  adr: number | null;
  hs_percent: number | null;
  first_kills: number;
  first_deaths: number;
}

export interface MapDetail {
  id: number;
  map_number: number;
  map_name: string;
  team1_score: number;
  team2_score: number;
  winner_id: number | null;
  player_stats: PlayerStat[];
}

export interface MatchPrediction {
  team1_id: number;
  team2_id: number;
  team1_win_prob: number;
  map_name: string | null;
  model_version: string;
  correct: boolean | null;
}

export interface MatchDetail extends MatchSummary {
  maps: MapDetail[];
  predictions: MatchPrediction[];
}

export interface PredictionItem {
  id: number;
  match_id: number | null;
  map_id: number | null;
  match_date: string | null;
  team1_id: number;
  team1_name: string;
  team2_id: number;
  team2_name: string;
  map_name: string | null;
  team1_win_prob: number;
  team2_win_prob: number;
  model_version: string;
  predicted_at: string;
  correct: boolean | null;
}

export interface AdHocPrediction {
  team1: { id: number; name: string };
  team2: { id: number; name: string };
  map_name: string | null;
  match_date: string;
  team1_win_prob: number;
  team2_win_prob: number;
  model_version: string;
}

export interface FoldMetric {
  month: string;
  accuracy: number;
  log_loss: number;
  brier_score: number;
}

export interface ModelAccuracy {
  model_version: string;
  model_type: string;
  trained_at: string;
  summary: Record<string, number>;
  rolling: FoldMetric[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  test: Record<string, any>;
  warning: string | null;
}

export interface FeatureImportanceItem {
  feature: string;
  importance: number;
}

export interface ModelFeatures {
  model_version: string;
  model_type: string;
  trained_at: string;
  features: FeatureImportanceItem[];
}

// --- API calls ---

export async function listTeams(search?: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (search) params.set("search", search);
  return fetchAPI<{ items: Team[]; count: number }>(`/api/teams?${params}`);
}

export async function getTeam(id: number) {
  return fetchAPI<TeamProfile>(`/api/teams/${id}`);
}

export async function getTeamPlayers(id: number) {
  return fetchAPI<{ team_id: number; team_name: string; players: PlayerInfo[] }>(
    `/api/teams/${id}/players`
  );
}

export async function listMatches(page = 1, pageSize = 25) {
  return fetchAPI<{ items: MatchSummary[]; page: number; page_size: number; total: number }>(
    `/api/matches?page=${page}&page_size=${pageSize}`
  );
}

export async function getMatch(id: number) {
  return fetchAPI<MatchDetail>(`/api/matches/${id}`);
}

export async function getUpcomingPredictions(limit = 25) {
  return fetchAPI<{ items: PredictionItem[]; count: number }>(
    `/api/predictions/upcoming?limit=${limit}`
  );
}

export async function getPredictionHistory(limit = 100) {
  return fetchAPI<{
    items: PredictionItem[];
    summary: { count: number; accuracy: number | null };
  }>(`/api/predictions/history?limit=${limit}`);
}

export async function predict(body: {
  team1_id?: number;
  team2_id?: number;
  team1?: string;
  team2?: string;
  map_name?: string | null;
}) {
  return fetchAPI<AdHocPrediction>("/api/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getModelAccuracy() {
  return fetchAPI<ModelAccuracy>("/api/model/accuracy");
}

export async function getModelFeatures() {
  return fetchAPI<ModelFeatures>("/api/model/features");
}
