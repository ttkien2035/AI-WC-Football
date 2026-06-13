import { useEffect, useState } from "react";
import { BarChart3, Brain, Database, RefreshCw, ShieldCheck } from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import {
  api, pct, type Analytics, type PipelineReview, type PipelineStatus, type ReviewRow,
} from "../api";
import { Card, Flag, StatusDot } from "../components/ui";
import { useT } from "../i18n";

export default function Pipeline({ onLogout }: { onLogout: () => void }) {
  const t = useT();
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [review, setReview] = useState<PipelineReview | null>(null);
  const [usage, setUsage] = useState<Analytics | null>(null);
  const [retraining, setRetraining] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    api.pipelineStatus().then(setStatus).catch((e) => setErr(String(e)));
    api.pipelineReview().then(setReview).catch(() => {});
    api.pipelineAnalytics().then(setUsage).catch(() => {});
  };
  useEffect(() => {
    load();
    const i = setInterval(load, 30_000);
    return () => clearInterval(i);
  }, []);

  const retrain = async () => {
    if (!confirm(t("pl.retrain_confirm"))) return;
    setRetraining(true);
    try {
      await api.mlRetrain();
      load();
    } finally {
      setRetraining(false);
    }
  };

  if (err) return <p className="text-red-500">{err}</p>;
  if (!status) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200/80 dark:bg-white/[0.1]" />;

  const c = status.collection;
  const counters: [string, number][] = [
    ["pl.matches", c.matches_total], ["pl.finished", c.finished],
    ["pl.live_now", c.live_now], ["pl.match_log", c.match_log],
    ["pl.prematch", c.prematch_snapshots], ["pl.timeline", c.timeline_series],
    ["pl.corner_teams", c.teams_with_corner_stats],
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <ShieldCheck size={18} className="text-emerald-500" /> {t("pl.heading")}
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-700 dark:bg-amber-950 dark:text-amber-300">
            {t("pl.admin_only")}
          </span>
        </h2>
        <button onClick={onLogout} className="text-xs text-slate-400 hover:underline">
          {t("pl.logout")}
        </button>
      </div>

      {/* data collection */}
      <Card>
        <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
          <Database size={14} /> {t("pl.collection")}
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {counters.map(([k, v]) => (
            <div key={k} className="rounded-xl bg-slate-100 p-2.5 text-center dark:bg-slate-800">
              <p className="text-[10px] uppercase tracking-wide text-slate-400">{t(k)}</p>
              <p className="text-lg font-bold tabular-nums">{v}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-400">
          {t("pl.scheduler", {
            t: status.scheduler.last_tick
              ? new Date(status.scheduler.last_tick).toLocaleTimeString()
              : "–",
            live: status.scheduler.live_mode ? "ON (60s)" : "off",
          })}
          <span className="ml-3 inline-flex items-center gap-2">
            {Object.entries(status.sources).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1">
                <StatusDot ok={v.ok} />{k.replace(/_/g, "-")}
              </span>
            ))}
          </span>
        </p>
      </Card>

      {/* ML status */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-1.5 text-sm font-semibold">
            <Brain size={14} /> {t("pl.ml")}
            <StatusDot ok={status.ml.available} />
          </h3>
          <button onClick={retrain}
            disabled={retraining || status.ml.retraining_now}
            className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-40">
            <RefreshCw size={12} className={retraining || status.ml.retraining_now ? "animate-spin" : ""} />
            {retraining || status.ml.retraining_now ? t("pl.retraining") : t("pl.retrain_now")}
          </button>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <Info label={t("pl.online_updates")} value={String(status.ml.online_updates_applied)} />
          <Info label={t("pl.last_retrain")} value={status.ml.last_retrain ?? "–"} />
          <Info label={t("pl.next_retrain")} value={status.ml.next_retrain_utc.replace("T", " ") + "Z"} />
          <Info label="Test RPS" value={status.ml.test_rps?.toFixed(4) ?? "–"} />
        </div>
        {status.elo_movers.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.movers")}</p>
            <div className="flex flex-wrap gap-1.5">
              {status.elo_movers.map((m) => (
                <span key={m.tla}
                  className={`rounded-lg px-2 py-0.5 text-xs font-semibold tabular-nums ${
                    m.delta > 0
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                      : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"}`}>
                  {m.tla} {m.delta > 0 ? "+" : ""}{m.delta}
                </span>
              ))}
            </div>
          </div>
        )}
        {/* factor scorecard: is each bounded nudge earning its keep? */}
        {status.factor_scorecard && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.scorecard")}</p>
            <table className="w-full text-xs tabular-nums">
              <thead>
                <tr className="text-left text-slate-400">
                  <th className="py-0.5">{t("pl.sc_factor")}</th><th>n</th>
                  <th>{t("pl.sc_with")}</th><th>{t("pl.sc_without")}</th><th>Δ</th><th></th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(status.factor_scorecard).map(([k, v]) => (
                  <tr key={k} className="border-t border-slate-100 dark:border-white/10">
                    <td className="py-1">{t(`pl.sc_${k}`)} <span className="text-slate-400">({v.metric})</span></td>
                    <td>{v.n}</td>
                    <td>{v.with?.toFixed(3) ?? "–"}</td>
                    <td>{v.without?.toFixed(3) ?? "–"}</td>
                    <td className={v.delta == null ? "" : v.delta < 0 ? "text-emerald-500 font-semibold" : v.delta > 0 ? "text-red-500 font-semibold" : ""}>
                      {v.delta?.toFixed(3) ?? "–"}
                    </td>
                    <td>{v.verdict === "helping" ? "✓" : v.verdict === "hurting" ? "✗" : v.verdict === "neutral" ? "≈" : "…"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-[10px] text-slate-400">{t("pl.sc_note")}</p>
          </div>
        )}
        {/* corners O/U calibration */}
        {status.corners_scorecard?.n > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.corners_sc")}</p>
            <p className="text-xs tabular-nums">
              n={status.corners_scorecard.n} · {t("pl.cs_hit")} <b>{status.corners_scorecard.hit_rate != null ? pct(status.corners_scorecard.hit_rate) : "–"}</b>
              {" · "}Brier <b>{status.corners_scorecard.brier ?? "–"}</b>
              {" · "}{t("pl.cs_pred")} {status.corners_scorecard.pred_mean_total} {t("pl.cs_vs")} {status.corners_scorecard.actual_mean_total}
            </p>
            <p className="mt-0.5 text-[11px] tabular-nums text-slate-400">
              🔄 {t("pl.cs_adapt")}: {status.corners_scorecard.club_base} → <b>{status.corners_scorecard.adaptive_base}</b>
              {status.corners_scorecard.observed_mean != null && <> ({t("pl.cs_obs")} {status.corners_scorecard.observed_mean})</>}
            </p>
          </div>
        )}
        {/* minute-sim timing calibration: scenario probs vs actual timing */}
        {status.sim_timing && Object.values(status.sim_timing).some((v) => v.n > 0) && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.sim_timing")}</p>
            <table className="w-full text-xs tabular-nums">
              <thead>
                <tr className="text-left text-slate-400">
                  <th className="py-0.5">{t("pl.st_scenario")}</th><th>n</th>
                  <th>{t("pl.st_pred")}</th><th>{t("pl.st_actual")}</th><th>Brier</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(status.sim_timing).filter(([, v]) => v.n > 0).map(([k, v]) => (
                  <tr key={k} className="border-t border-slate-100 dark:border-white/10">
                    <td className="py-1">{t(`pl.st_${k}`)}</td>
                    <td>{v.n}</td>
                    <td>{v.pred_mean != null ? pct(v.pred_mean) : "–"}</td>
                    <td>{v.actual_rate != null ? pct(v.actual_rate) : "–"}</td>
                    <td>{v.brier?.toFixed(3) ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {/* meta-calibrated blend weights */}
        {status.meta_weights && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.meta_w")}</p>
            {status.meta_weights.served ? (
              <p className="text-xs">
                {["market", "ml", "poisson"].map((k) => (
                  <span key={k} className="mr-3">
                    {k}: <b>{status.meta_weights.served![k]}</b>
                    <span className="text-slate-400"> ({t("pl.meta_hand")} {status.meta_weights.hand[k]})</span>
                  </span>
                ))}
                <span className="text-slate-400">
                  n={status.meta_weights.n} · RPS {status.meta_weights.rps_fitted} {t("pl.meta_vs")} {status.meta_weights.rps_hand}
                </span>
              </p>
            ) : (
              <p className="text-xs text-slate-400">
                {t("pl.meta_waiting", { n: String(status.meta_weights.n) })}
              </p>
            )}
          </div>
        )}
      </Card>

      {usage && <UsageCard usage={usage} />}

      {/* prediction vs result review */}
      <Card>
        <h3 className="mb-2 text-sm font-semibold">{t("pl.review")}</h3>
        {!review?.summary ? (
          <p className="text-sm text-slate-400">{t("pl.no_finished")}</p>
        ) : (
          <>
            <p className="mb-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
              {t("pl.review_sum", {
                c: review.summary.correct, n: review.summary.n,
                pct: pct(review.summary.accuracy),
                rps: review.summary.rps.toFixed(3),
                ll: review.summary.logloss.toFixed(3),
              })}
            </p>
            <div className="space-y-2">
              {review.matches.map((r) => <ReviewCard key={r.match_id} r={r} />)}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

function UsageCard({ usage }: { usage: Analytics }) {
  const t = useT();
  const tooltipStyle = { background: "#0f172a", border: "1px solid #334155",
                         borderRadius: 8, color: "#f1f5f9" };
  if (usage.totals.events === 0) {
    return (
      <Card>
        <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
          <BarChart3 size={14} /> {t("pl.usage")}
        </h3>
        <p className="text-sm text-slate-400">{t("pl.no_usage")}</p>
      </Card>
    );
  }
  return (
    <Card>
      <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
        <BarChart3 size={14} /> {t("pl.usage")}
      </h3>
      {/* KPI strip */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Kpi label={t("pl.k_visitors")} value={usage.kpis.visitors} />
        <Kpi label={t("pl.k_active")} value={usage.kpis.active_today}
          sub={t("pl.vs_yday", { n: usage.kpis.active_yesterday })}
          trend={usage.kpis.active_today - usage.kpis.active_yesterday} />
        <Kpi label={t("pl.k_engage")} value={usage.kpis.events_per_visitor} />
        <Kpi label={t("pl.k_returning")} value={`${usage.kpis.returning_pct}%`}
          sub={`${usage.kpis.returning}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.daily")}</p>
          <div style={{ height: 180 }}>
            <ResponsiveContainer>
              <AreaChart data={usage.daily} margin={{ left: -16, right: 4 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="date" stroke="#94a3b8" fontSize={10}
                  tickFormatter={(d) => d.slice(5)} />
                <YAxis stroke="#94a3b8" fontSize={10} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area dataKey="events" name={t("pl.events")}
                  stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.25} />
                <Area dataKey="visitors" name={t("pl.visitors")}
                  stroke="#10b981" fill="#10b981" fillOpacity={0.45} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.top_matchups")}</p>
          <div style={{ height: 180 }}>
            <ResponsiveContainer>
              <BarChart data={usage.matchups} layout="vertical" margin={{ left: 8, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.15} />
                <XAxis type="number" stroke="#94a3b8" fontSize={10} allowDecimals={false} />
                <YAxis type="category" dataKey="pair" width={76} stroke="#94a3b8" fontSize={10} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="n" fill="#10b981" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* hourly peak + feature reach */}
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.hourly")}</p>
          <div style={{ height: 150 }}>
            <ResponsiveContainer>
              <BarChart data={usage.hourly.map((h) => ({
                hour: `${((h.hour + new Date().getTimezoneOffset() / -60 + 24) % 24)}h`,
                n: h.n }))} margin={{ left: -20, right: 4 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="hour" stroke="#94a3b8" fontSize={9} interval={2} />
                <YAxis stroke="#94a3b8" fontSize={9} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="n" fill="#f59e0b" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.features")}</p>
          {usage.features.map((x) => {
            const max = usage.features[0]?.visitors || 1;
            return (
              <div key={x.feature} className="mb-1 flex items-center gap-2 text-xs">
                <span className="w-24 shrink-0">{t(`feat.${x.feature}`)}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded bg-slate-200/80 dark:bg-white/[0.1]">
                  <div className="h-full rounded bg-emerald-500"
                       style={{ width: `${(x.visitors / max) * 100}%` }} />
                </div>
                <span className="w-8 text-right tabular-nums">{x.visitors}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.top_tabs")}</p>
          {usage.tabs.map((x) => {
            const max = usage.tabs[0]?.n || 1;
            return (
              <div key={x.tab} className="mb-1 flex items-center gap-2 text-xs">
                <span className="w-20 shrink-0">{x.tab}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded bg-slate-200/80 dark:bg-white/[0.1]">
                  <div className="h-full rounded bg-sky-500"
                       style={{ width: `${(x.n / max) * 100}%` }} />
                </div>
                <span className="w-10 text-right tabular-nums">{x.n}</span>
              </div>
            );
          })}
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">{t("pl.lang_split")}</p>
          <div className="flex gap-2">
            {usage.langs.map((x) => (
              <span key={x.lang}
                className="rounded-lg bg-slate-100 px-3 py-1.5 text-sm font-semibold tabular-nums dark:bg-slate-800">
                {x.lang.toUpperCase()}: {x.n}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

function Kpi({ label, value, sub, trend }: {
  label: string; value: number | string; sub?: string; trend?: number;
}) {
  return (
    <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-white/[0.07]">
      <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="flex items-baseline gap-1 text-xl font-bold tabular-nums">
        {value}
        {trend != null && trend !== 0 && (
          <span className={`text-[11px] ${trend > 0 ? "text-emerald-500" : "text-red-400"}`}>
            {trend > 0 ? "▲" : "▼"}{Math.abs(trend)}
          </span>
        )}
      </p>
      {sub && <p className="text-[10px] text-slate-400">{sub}</p>}
    </div>
  );
}

function ReviewCard({ r }: { r: ReviewRow }) {
  const t = useT();
  const tagColor: Record<string, string> = {
    confident_hit: "bg-emerald-600 text-white",
    hit: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
    near_miss: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    upset: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
    big_upset: "bg-red-600 text-white",
  };
  const f = r.factors;
  const factors: string[] = [];
  if (f.red_cards && (f.red_cards.home > 0 || f.red_cards.away > 0)) {
    factors.push(`🟥 ${f.red_cards.home}–${f.red_cards.away}`);
  }
  if (f.ht_swing) factors.push(`🔄 ${t("pl.f_ht_swing")}`);
  if (f.absence) factors.push(`⚠ ${t("pl.f_absence")}`);
  if (f.corners?.home != null) factors.push(`⛳ ${f.corners.home}–${f.corners.away}`);

  return (
    <div className="rounded-xl border border-slate-200 p-3 text-sm dark:border-white/10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 font-semibold">
          <Flag crest={r.home.crest} tla={r.home.tla} />
          {r.home.tla} <b className="tabular-nums">{r.score.home}–{r.score.away}</b> {r.away.tla}
          <Flag crest={r.away.crest} tla={r.away.tla} />
          {r.ht_score?.home != null && (
            <span className="text-xs text-slate-400">(HT {r.ht_score.home}–{r.ht_score.away})</span>
          )}
        </span>
        <span className="flex items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${tagColor[r.tag] ?? ""}`}>
            {r.correct ? "✓" : "✗"} {t(`tag.${r.tag}`)}
          </span>
          <span className="text-xs text-slate-400">{r.date.slice(0, 10)}</span>
        </span>
      </div>

      {/* pre-match probability strip */}
      <div className="mt-2 flex h-3 w-full overflow-hidden rounded-full text-[9px] leading-3 text-white">
        <div className="bg-emerald-500 text-center" style={{ width: `${r.probs.home * 100}%` }}>
          {r.probs.home > 0.12 && pct(r.probs.home, 0)}
        </div>
        <div className="bg-slate-400 text-center" style={{ width: `${r.probs.draw * 100}%` }}>
          {r.probs.draw > 0.12 && pct(r.probs.draw, 0)}
        </div>
        <div className="bg-sky-500 text-center" style={{ width: `${r.probs.away * 100}%` }}>
          {r.probs.away > 0.12 && pct(r.probs.away, 0)}
        </div>
      </div>

      <p className="mt-1.5 text-xs tabular-nums text-slate-500 dark:text-slate-400">
        {t("common.predicted")}: <b>{r.predicted}</b> → {t("common.actual")}: <b>{r.actual}</b>
        {" "}· P({r.actual}) = <b>{pct(r.p_actual)}</b>
        {" "}· <span className="opacity-70">
          {r.probs_source === "prematch_snapshot" ? t("pl.snapshot") : t("pl.asof")}
        </span>
        {r.elo_shift && (
          <span className="ml-2">
            {t("pl.elo_shift")}: {r.home.tla} {r.elo_shift.home > 0 ? "+" : ""}{r.elo_shift.home},
            {" "}{r.away.tla} {r.elo_shift.away > 0 ? "+" : ""}{r.elo_shift.away}
          </span>
        )}
      </p>
      {factors.length > 0 && (
        <p className="mt-1 text-xs text-slate-400">{factors.join("  ·  ")}</p>
      )}

      {/* factor-by-factor comparison */}
      {r.compare && (
        <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200/60 dark:border-white/10">
          <table className="w-full min-w-[420px] text-xs tabular-nums">
            <thead>
              <tr className="bg-slate-100/80 text-left text-[10px] uppercase text-slate-400 dark:bg-white/[0.05]">
                <th className="px-2 py-1">{t("pl.c_factor")}</th>
                <th className="px-2 py-1">{t("pl.c_pred")}</th>
                <th className="px-2 py-1">{t("pl.c_actual")}</th>
                <th className="px-2 py-1"></th>
              </tr>
            </thead>
            <tbody>
              <CmpRow label={t("pl.c_winner")} pred={r.compare.winner.pred}
                actual={r.compare.winner.actual} hit={r.compare.winner.hit} />
              <CmpRow label={t("pl.c_score")} pred={r.compare.score.pred ?? "–"}
                actual={r.compare.score.actual} hit={r.compare.score.hit} gold={r.compare.score.hit} />
              <CmpRow label={t("pl.c_goals")}
                pred={r.compare.total_goals.pred_xg != null ? `xG ${r.compare.total_goals.pred_xg}` : "–"}
                actual={String(r.compare.total_goals.actual)} />
              <CmpRow label={t("pl.c_o25")}
                pred={r.compare.over25.pred_p != null ? pct(r.compare.over25.pred_p) : "–"}
                actual={r.compare.over25.actual ? "✓" : "✗"}
                hit={r.compare.over25.pred_p != null
                  ? (r.compare.over25.pred_p > 0.5) === r.compare.over25.actual : undefined} />
              <CmpRow label={t("pl.c_btts")}
                pred={r.compare.btts.pred_p != null ? pct(r.compare.btts.pred_p) : "–"}
                actual={r.compare.btts.actual ? "✓" : "✗"}
                hit={r.compare.btts.pred_p != null
                  ? (r.compare.btts.pred_p > 0.5) === r.compare.btts.actual : undefined} />
              {(() => {
                const c = r.compare!.corners as any;
                const ouWord = (k: string) =>
                  k === "over" ? t("match.over") : k === "under" ? t("match.under") : t("match.push");
                if (c.line != null && c.pick) {
                  return (
                    <CmpRow
                      label={`${t("pl.c_corners")} ${c.line}`}
                      pred={`${ouWord(c.pick)} (${pct(c.pick === "over" ? c.p_over : 1 - c.p_over, 0)})${
                        c.expected_total != null ? ` · ~${c.expected_total}` : ""}`}
                      actual={c.actual_total != null
                        ? `${c.actual_total}${c.detail ? ` (${c.detail.home}–${c.detail.away})` : ""} → ${
                            c.actual ? ouWord(c.actual) : "–"}`
                        : "–"}
                      hit={c.hit}
                    />
                  );
                }
                return (
                  <CmpRow label={t("pl.c_corners")}
                    pred={c.pred != null ? `~${c.pred}` : "–"}
                    actual={c.actual != null ? String(c.actual) : "–"} />
                );
              })()}
            </tbody>
          </table>
        </div>
      )}

      {/* cause analysis + model update */}
      {r.notes && r.notes.length > 0 && (
        <div className="mt-2 rounded-lg bg-sky-50 p-2 text-xs leading-5 dark:bg-sky-950/30">
          <p className="mb-0.5 font-semibold text-sky-700 dark:text-sky-300">🔍 {t("pl.analysis")}</p>
          {r.notes.map((n, i) => <p key={i}>• {t(n.key, n.params)}</p>)}
          {r.improve && (
            <p className="mt-1 font-medium text-amber-600 dark:text-amber-400">
              🛠 {t("pl.improve")}: {t(r.improve)}
            </p>
          )}
          {r.elo_shift && (
            <p className="mt-1 text-slate-500 dark:text-slate-400">
              {t("pl.model_update", {
                h: r.home.tla ?? "?", dh: (r.elo_shift.home > 0 ? "+" : "") + r.elo_shift.home,
                a: r.away.tla ?? "?", da: (r.elo_shift.away > 0 ? "+" : "") + r.elo_shift.away,
              })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function CmpRow({ label, pred, actual, hit, gold }: {
  label: string; pred: string; actual: string; hit?: boolean; gold?: boolean;
}) {
  return (
    <tr className="border-t border-slate-100 dark:border-white/10">
      <td className="px-2 py-1 text-slate-500 dark:text-slate-400">{label}</td>
      <td className="px-2 py-1 font-medium">{pred}</td>
      <td className="px-2 py-1 font-medium">{actual}</td>
      <td className="px-2 py-1">
        {gold ? <span className="font-bold text-amber-500">🎯</span>
          : hit === true ? <span className="font-bold text-emerald-500">✓</span>
          : hit === false ? <span className="font-bold text-red-400">✗</span> : null}
      </td>
    </tr>
  );
}

const Info = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800">
    <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
    <p className="text-sm font-semibold tabular-nums">{value}</p>
  </div>
);
