import { useEffect, useState } from "react";
import { Brain, Database, RefreshCw, ShieldCheck } from "lucide-react";
import {
  api, adminToken, pct, type PipelineReview, type PipelineStatus, type ReviewRow,
} from "../api";
import { Card, Flag, StatusDot } from "../components/ui";
import { useT } from "../i18n";

export default function Pipeline({ onLogout }: { onLogout: () => void }) {
  const t = useT();
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [review, setReview] = useState<PipelineReview | null>(null);
  const [retraining, setRetraining] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    api.pipelineStatus().then(setStatus).catch((e) => setErr(String(e)));
    api.pipelineReview().then(setReview).catch(() => {});
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
  if (!status) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />;

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
      </Card>

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
    <div className="rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-800">
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
    </div>
  );
}

const Info = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800">
    <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
    <p className="text-sm font-semibold tabular-nums">{value}</p>
  </div>
);
