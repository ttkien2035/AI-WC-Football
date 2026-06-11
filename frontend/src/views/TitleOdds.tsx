import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Simulation, type TeamRow, pct } from "../api";
import { Card } from "../components/ui";
import { useT } from "../i18n";

const METRICS = [
  { key: "champion", label: "title.champion" },
  { key: "final", label: "title.final" },
  { key: "sf", label: "title.sf" },
  { key: "qf", label: "title.qf" },
  { key: "r16", label: "title.r16" },
  { key: "r32", label: "title.r32" },
] as const;
type MetricKey = (typeof METRICS)[number]["key"];

export default function TitleOdds() {
  const t = useT();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [teams, setTeams] = useState<Record<string, TeamRow> | null>(null);
  const [metric, setMetric] = useState<MetricKey>("champion");

  useEffect(() => {
    api.simulate().then(setSim);
    api.teams().then(setTeams);
  }, []);

  const data = useMemo(() => {
    if (!sim) return [];
    return Object.entries(sim.teams)
      .map(([tla, v]) => ({ tla, name: teams?.[tla]?.name ?? tla, value: v[metric] }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 20);
  }, [sim, teams, metric]);

  if (!sim) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />;

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">
          {t("title.heading", { metric: t(METRICS.find((m) => m.key === metric)?.label ?? "") })}
        </h2>
        <div className="flex flex-wrap gap-1">
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMetric(m.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                metric === m.key
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-200 text-slate-600 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              {t(m.label)}
            </button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        {t("title.note", {
          runs: sim.runs.toLocaleString(),
          time: new Date(sim.computed_at).toLocaleString(),
        })}
      </p>
      <div style={{ height: 560 }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 28 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="currentColor" opacity={0.1} />
            <XAxis type="number" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} stroke="#94a3b8" fontSize={11} />
            <YAxis type="category" dataKey="tla" width={48} stroke="#94a3b8" fontSize={12} />
            <Tooltip
              formatter={(v: number) => pct(v)}
              labelFormatter={(tla: string) => data.find((d) => d.tla === tla)?.name ?? tla}
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, color: "#f1f5f9" }}
            />
            <Bar dataKey="value" fill="#10b981" radius={[0, 6, 6, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
