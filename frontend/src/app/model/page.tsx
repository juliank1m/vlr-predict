"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
  ReferenceLine,
} from "recharts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Brain, BarChart3, Activity } from "lucide-react";
import {
  getModelAccuracy,
  getModelFeatures,
  getPredictionHistory,
  type ModelAccuracy,
  type FeatureImportanceItem,
  type PredictionItem,
} from "@/lib/api";

export default function ModelPage() {
  const [accuracy, setAccuracy] = useState<ModelAccuracy | null>(null);
  const [features, setFeatures] = useState<FeatureImportanceItem[]>([]);
  const [historyItems, setHistoryItems] = useState<PredictionItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getModelAccuracy().catch(() => null),
      getModelFeatures().catch(() => ({ features: [] })),
      getPredictionHistory(50).catch(() => ({ items: [], summary: { count: 0, accuracy: null } })),
    ]).then(([acc, feat, hist]) => {
      setAccuracy(acc);
      setFeatures(feat.features ?? []);
      setHistoryItems(hist.items ?? []);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    );
  }

  if (!accuracy) {
    return (
      <p className="text-muted-foreground">
        Model metadata not available. Train a model first.
      </p>
    );
  }

  const rollingData = accuracy.rolling.map((f) => ({
    month: f.month.slice(0, 7),
    accuracy: +(f.accuracy * 100).toFixed(1),
    log_loss: +f.log_loss.toFixed(4),
  }));

  const topFeatures = features
    .sort((a, b) => b.importance - a.importance)
    .slice(0, 20)
    .reverse();

  // Calibration curve data
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const calibrationBins: { bin: number; range: number[]; count: number; avg_predicted: number | null; actual_rate: number | null }[] = accuracy.test?.calibration ?? [];
  const calibrationData = calibrationBins
    .filter((b) => b.avg_predicted != null && b.actual_rate != null)
    .map((b) => ({
      predicted: +(b.avg_predicted! * 100).toFixed(1),
      actual: +(b.actual_rate! * 100).toFixed(1),
      count: b.count,
    }));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Model Performance</h1>
        <p className="text-muted-foreground">
          {accuracy.model_type} ({accuracy.model_version}) — trained{" "}
          {new Date(accuracy.trained_at).toLocaleDateString()}
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {(() => {
          const fm = accuracy.test.full_model ?? accuracy.test;
          return [
            {
              label: "Test Accuracy",
              value: fm.accuracy
                ? `${(fm.accuracy * 100).toFixed(1)}%`
                : "—",
            },
            {
              label: "Test Log-Loss",
              value: fm.log_loss
                ? fm.log_loss.toFixed(4)
                : "—",
            },
            {
              label: "Test Brier",
              value: fm.brier_score
                ? fm.brier_score.toFixed(4)
                : "—",
            },
            {
              label: "CV Folds",
              value: String(accuracy.rolling.length),
            },
          ];
        })().map((stat) => (
          <Card key={stat.label} className="border-t-2 border-t-primary">
            <CardContent className="pt-6 text-center">
              <p className="text-2xl font-bold">{stat.value}</p>
              <p className="text-xs text-muted-foreground">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Calibration curve */}
      {calibrationData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Brain size={16} className="text-primary" />
              Calibration Curve
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis
                  type="number"
                  dataKey="predicted"
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                  label={{ value: "Predicted (%)", position: "insideBottom", offset: -5, fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="actual"
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                  label={{ value: "Actual (%)", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <Tooltip
                  formatter={(v, name) => [`${v}%`, name === "actual" ? "Actual Win %" : "Predicted %"]}
                  labelFormatter={() => ""}
                />
                <ReferenceLine
                  segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]}
                  stroke="var(--color-muted-foreground)"
                  strokeDasharray="5 5"
                />
                <Scatter data={calibrationData} fill="var(--color-primary)" />
              </ScatterChart>
            </ResponsiveContainer>
            <p className="text-xs text-muted-foreground text-center mt-2">
              Points near the diagonal indicate well-calibrated probabilities.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Rolling accuracy chart */}
      {rollingData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Activity size={16} className="text-accent" />
              Rolling Accuracy by Validation Month
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={rollingData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 10 }}
                  interval={Math.max(0, Math.floor(rollingData.length / 12))}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip formatter={(v) => `${v}%`} />
                <Line
                  type="monotone"
                  dataKey="accuracy"
                  stroke="var(--color-primary)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Rolling log-loss chart */}
      {rollingData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Rolling Log-Loss by Validation Month
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={rollingData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 10 }}
                  interval={Math.max(0, Math.floor(rollingData.length / 12))}
                />
                <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="log_loss"
                  stroke="var(--color-destructive)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Feature importance */}
      {topFeatures.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BarChart3 size={16} className="text-primary" />
              Top 20 Feature Importances
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={500}>
              <BarChart data={topFeatures} layout="vertical" margin={{ left: 140 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="feature"
                  tick={{ fontSize: 11 }}
                  width={130}
                />
                <Tooltip />
                <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                  {topFeatures.map((_, i) => (
                    <Cell
                      key={i}
                      fill={`oklch(0.63 0.24 25 / ${0.4 + (i / topFeatures.length) * 0.6})`}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Prediction log */}
      {historyItems.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Prediction Log</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Match</TableHead>
                  <TableHead>Map</TableHead>
                  <TableHead className="text-right">Prediction</TableHead>
                  <TableHead className="text-center">Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {historyItems.map((p) => {
                  const favored = p.team1_win_prob >= 0.5 ? p.team1_name : p.team2_name;
                  const prob = Math.max(p.team1_win_prob, p.team2_win_prob);
                  return (
                    <TableRow key={p.id}>
                      <TableCell className="text-xs text-muted-foreground">
                        {p.match_date
                          ? new Date(p.match_date).toLocaleDateString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {p.team1_name} vs {p.team2_name}
                      </TableCell>
                      <TableCell className="text-xs">{p.map_name ?? "—"}</TableCell>
                      <TableCell className="text-right text-xs font-mono">
                        {favored} {(prob * 100).toFixed(0)}%
                      </TableCell>
                      <TableCell className="text-center">
                        {p.correct === true && (
                          <Badge variant="default" className="bg-green-600">Correct</Badge>
                        )}
                        {p.correct === false && (
                          <Badge variant="secondary" className="bg-red-500 text-white">Wrong</Badge>
                        )}
                        {p.correct === null && (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
