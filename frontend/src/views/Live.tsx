import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Radio } from "lucide-react";
import {
  api, type Match, type Prediction, type TimelinePoint, pct,
} from "../api";
import { Card, Flag, ProbBar } from "../components/ui";
import ResultsCard, { StatBars } from "../components/ResultsCard";
import { useT } from "../i18n";

const POLL_MS = 20_000;

export default function Live() {
  const t = useT();
  const [live, setLive] = useState<Match[]>([]);
  const [today, setToday] = useState<Match[]>([]);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    const poll = () =>
      api.live().then((d) => {
        setLive(d.live);
        setToday(d.today);
        setSelected((cur) =>
          cur && d.live.some((m) => m.id === cur) ? cur : d.live[0]?.id ?? null);
      }).catch(() => {});
    poll();
    const i = setInterval(poll, POLL_MS);
    return () => clearInterval(i);
  }, []);

  const match = live.find((m) => m.id === selected) ?? null;

  if (live.length === 0) {
    return (
      <div className="space-y-4">
        <NoLive today={today} />
        <ResultsCard limit={6} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {live.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {live.map((m) => (
            <button key={m.id} onClick={() => setSelected(m.id)}
              className={`rounded-full px-3 py-1.5 text-sm font-semibold ${
                m.id === selected ? "bg-red-600 text-white"
                  : "bg-slate-200/80 dark:bg-white/[0.1]"}`}>
              {m.home.tla} {m.score.home ?? 0}–{m.score.away ?? 0} {m.away.tla}
            </button>
          ))}
        </div>
      )}
      {match && <LiveMatch match={match} />}
      <p className="text-center text-[11px] text-slate-400">{t("live.updated")}</p>
    </div>
  );
}

function LiveMatch({ match }: { match: Match }) {
  const t = useT();
  const [pred, setPred] = useState<Prediction | null>(null);
  const [points, setPoints] = useState<TimelinePoint[]>([]);

  useEffect(() => {
    if (!match.home.tla || !match.away.tla) return;
    const poll = () => {
      api.predict(match.home.tla!, match.away.tla!).then(setPred).catch(() => {});
      api.timeline(match.id).then((d) => setPoints(d.points)).catch(() => {});
    };
    poll();
    const i = setInterval(poll, POLL_MS);
    return () => clearInterval(i);
  }, [match.id, match.home.tla, match.away.tla]);

  const chartData = useMemo(
    () => points.filter((p) => p.minute != null).map((p) => ({
      minute: p.minute,
      home: +(p.probs.home * 100).toFixed(1),
      draw: +(p.probs.draw * 100).toFixed(1),
      away: +(p.probs.away * 100).toFixed(1),
    })),
    [points],
  );

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <div className="space-y-4">
        {/* score header */}
        <Card>
          <div className="flex flex-wrap items-center justify-center gap-3 text-lg font-extrabold sm:gap-6 sm:text-2xl">
            <span className="flex items-center gap-2">
              <Flag crest={match.home.crest} tla={match.home.tla} size={32} /> {match.home.name}
            </span>
            <span className="rounded-xl bg-red-100 px-4 py-2 tabular-nums text-red-600 dark:bg-red-950 dark:text-red-300">
              {match.score.home ?? 0}–{match.score.away ?? 0}
            </span>
            <span className="flex items-center gap-2">
              {match.away.name} <Flag crest={match.away.crest} tla={match.away.tla} size={32} />
            </span>
          </div>
          <p className="mt-1 flex items-center justify-center gap-2 text-sm text-red-500">
            <Radio size={14} className="animate-pulse" />
            {match.minute_estimate != null && <b>{match.minute_estimate}'</b>}
            {match.minute_source !== "livescore" && match.minute_estimate != null && " (~)"}
            {match.ht_score && ` · HT ${match.ht_score.home}–${match.ht_score.away}`}
            {match.red_cards && (match.red_cards.home > 0 || match.red_cards.away > 0) &&
              ` · 🟥 ${match.red_cards.home}–${match.red_cards.away}`}
          </p>
          {pred && (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-semibold text-slate-400">{t("live.winprob")}</p>
              <ProbBar label={match.home.tla ?? ""} p={pred.probs.home} color="bg-emerald-500" />
              <ProbBar label={t("match.draw")} p={pred.probs.draw} color="bg-slate-400" />
              <ProbBar label={match.away.tla ?? ""} p={pred.probs.away} color="bg-sky-500" />
            </div>
          )}
        </Card>

        {/* probability timeline */}
        <Card>
          <h3 className="mb-2 text-sm font-semibold">{t("live.chart")}</h3>
          {chartData.length < 2 ? (
            <p className="py-10 text-center text-xs text-slate-400">{t("live.chart_empty")}</p>
          ) : (
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <AreaChart data={chartData} stackOffset="expand" margin={{ left: 0, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="minute" stroke="#94a3b8" fontSize={11}
                    tickFormatter={(v) => `${v}'`} />
                  <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`}
                    stroke="#94a3b8" fontSize={11} />
                  <Tooltip
                    formatter={(v: number, name: string) => [`${v}%`, name]}
                    labelFormatter={(m) => `${m}'`}
                    contentStyle={{ background: "#0f172a", border: "1px solid #334155",
                                    borderRadius: 8, color: "#f1f5f9" }} />
                  <Area dataKey="home" name={match.home.tla ?? "H"} stackId="1"
                    stroke="#10b981" fill="#10b981" fillOpacity={0.7} />
                  <Area dataKey="draw" name="X" stackId="1"
                    stroke="#64748b" fill="#64748b" fillOpacity={0.5} />
                  <Area dataKey="away" name={match.away.tla ?? "A"} stackId="1"
                    stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.7} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* events feed */}
        <Card>
          <h3 className="mb-2 text-sm font-semibold">{t("live.events")}</h3>
          {!match.incidents?.length ? (
            <p className="text-xs text-slate-400">{t("live.no_events")}</p>
          ) : (
            <div className="space-y-1">
              {[...match.incidents].reverse().map((ev, i) => (
                <p key={i} className="text-sm tabular-nums">
                  <span className="mr-1 inline-block w-9 text-right text-xs text-slate-400">
                    {ev.minute != null ? `${ev.minute}'` : "–"}
                  </span>
                  {ev.type === "goal" ? "⚽" : ev.type === "red" ? "🟥" : "🟨"}{" "}
                  <b>{ev.side === "home" ? match.home.tla : ev.side === "away" ? match.away.tla : "?"}</b>{" "}
                  {ev.player ?? ""}
                  {ev.own_goal && ` (${t("live.own_goal")})`}
                  {ev.penalty && ` (${t("live.pen")})`}
                </p>
              ))}
            </div>
          )}
          {match.stats && (
            <StatBars stats={match.stats} home={match.home.tla} away={match.away.tla} />
          )}
        </Card>
      </div>

      <LineupsCard match={match} />
    </div>
  );
}

function LineupsCard({ match }: { match: Match }) {
  const t = useT();
  return (
    <Card>
      <h3 className="mb-2 text-sm font-semibold">{t("live.lineups")}</h3>
      {!match.lineups?.home && !match.lineups?.away ? (
        <p className="text-xs text-slate-400">{t("live.lineups_tba")}</p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {(["home", "away"] as const).map((side) => {
            const lu = match.lineups?.[side];
            const team = match[side];
            return (
              <div key={side}>
                <p className="mb-1 flex items-center gap-1.5 text-xs font-bold">
                  <Flag crest={team.crest} tla={team.tla} size={16} /> {team.tla}
                  {lu?.formation && (
                    <span className="rounded bg-emerald-100 px-1.5 text-[10px] text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                      {lu.formation}
                    </span>
                  )}
                </p>
                {lu?.players?.map((p, i) => (
                  <p key={i} className="text-[11px] leading-5 text-slate-600 dark:text-slate-300">
                    <span className="inline-block w-5 text-right text-slate-400">{p.shirt ?? ""}</span>{" "}
                    {p.name}
                  </p>
                )) ?? <p className="text-[11px] text-slate-400">—</p>}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function NoLive({ today }: { today: Match[] }) {
  const t = useT();
  const upcoming = today.filter((m) => m.status === "TIMED" || m.status === "SCHEDULED");
  return (
    <Card>
      <p className="mb-3 text-center text-sm text-slate-400">{t("live.none")}</p>
      {upcoming.length > 0 && (
        <>
          <h3 className="mb-2 text-sm font-semibold">{t("live.upcoming")}</h3>
          <div className="space-y-2">
            {upcoming.map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
                <span className="flex items-center gap-2">
                  <Flag crest={m.home.crest} tla={m.home.tla} /> {m.home.name}
                  <span className="text-slate-400">vs</span>
                  {m.away.name} <Flag crest={m.away.crest} tla={m.away.tla} />
                </span>
                <span className="flex items-center gap-2 text-xs tabular-nums text-slate-400">
                  {m.lineups?.home && (
                    <span className="rounded bg-emerald-100 px-1.5 text-[10px] text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                      XI ✓
                    </span>
                  )}
                  {new Date(m.utcDate).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
      {upcoming.some((m) => m.lineups?.home) && (
        <div className="mt-3">
          {upcoming.filter((m) => m.lineups?.home).map((m) => (
            <LineupsCard key={m.id} match={m} />
          ))}
        </div>
      )}
    </Card>
  );
}
