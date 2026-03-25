"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import {
  getModelAccuracy,
  getModelFeatures,
  type ModelAccuracy,
  type FeatureImportanceItem,
} from "@/lib/api";

export default function ModelPage() {
  const [accuracy, setAccuracy] = useState<ModelAccuracy | null>(null);
  const [features, setFeatures] = useState<FeatureImportanceItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getModelAccuracy().catch(() => null),
      getModelFeatures().catch(() => ({ features: [] })),
    ]).then(([acc, feat]) => {
      setAccuracy(acc);
      setFeatures(feat.features ?? []);
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
        {[
          {
            label: "Test Accuracy",
            value: accuracy.test.accuracy
              ? `${(accuracy.test.accuracy * 100).toFixed(1)}%`
              : "—",
          },
          {
            label: "Test Log-Loss",
            value: accuracy.test.log_loss
              ? accuracy.test.log_loss.toFixed(4)
              : "—",
          },
          {
            label: "Test Brier",
            value: accuracy.test.brier_score
              ? accuracy.test.brier_score.toFixed(4)
              : "—",
          },
          {
            label: "CV Folds",
            value: String(accuracy.rolling.length),
          },
        ].map((stat) => (
          <Card key={stat.label}>
            <CardContent className="pt-6 text-center">
              <p className="text-2xl font-bold">{stat.value}</p>
              <p className="text-xs text-muted-foreground">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Rolling accuracy chart */}
      {rollingData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Rolling Accuracy by Validation Month
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={rollingData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
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
                  stroke="hsl(var(--primary))"
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
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
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
                  stroke="hsl(var(--destructive))"
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
            <CardTitle className="text-base">Top 20 Feature Importances</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={500}>
              <BarChart data={topFeatures} layout="vertical" margin={{ left: 140 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
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
                      fill={`hsl(var(--primary) / ${0.4 + (i / topFeatures.length) * 0.6})`}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
