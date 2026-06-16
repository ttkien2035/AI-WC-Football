import { useEffect, useState } from "react";
import { api, type EvalResult, type MlStatus, type TeamRow, type TournamentEval, pct } from "../api";
import { Card, Flag } from "../components/ui";
import { useT } from "../i18n";

export default function Accuracy() {
  const t = useT();
  const [status, setStatus] = useState<MlStatus | null>(null);
  const [teams, setTeams] = useState<Record<string, TeamRow>>({});
  const [mode, setMode] = useState<"team" | "h2h">("team");
  const [team1, setTeam1] = useState("BRA");
  const [team2, setTeam2] = useState("ARG");
  const [result, setResult] = useState<EvalResult | null>(null);
  const [tour, setTour] = useState<TournamentEval | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.mlStatus().then(setStatus);
    api.teams().then(setTeams);
    api.evalTournament().then(setTour).catch(() => {});
  }, []);

  const check = async () => {
    setLoading(true);
    try {
      setResult(mode === "team"
        ? await api.evalTeam(team1)
        : await api.evalH2h(team1, team2));
    } finally {
      setLoading(false);
    }
  };

  const tlas = Object.values(teams).sort((a, b) => a.name.localeCompare(b.name));
  const metrics = status?.report?.test_metrics;

  // a compact per-target verdict chip: label + predicted value + hit/miss/exact
  const verdict = (label: string, value: string,
                   state: "exact" | "hit" | "miss" | null, title?: string) => (
    <span title={title}
      className="inline-flex items-center gap-1 rounded-full bg-white/70 px-2 py-0.5 text-[11px] dark:bg-white/[0.06]">
      <span className="text-slate-400">{label}</span>
      <b className="text-slate-700 dark:text-slate-200">{value}</b>
      {state === "exact" ? <span>🎯</span>
        : state === "hit" ? <span className="font-bold text-emerald-500">✓</span>
        : state === "miss" ? <span className="font-bold text-red-400">✗</span> : null}
    </span>
  );

  return (
    <div className="space-y-4">
      {tour && tour.matches.length > 0 && (
        <Card>
          <h2 className="mb-1 text-lg font-bold">{t("acc.wc_heading")}</h2>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">{t("acc.wc_note")}</p>
          {tour.summary && (
            <p className="mb-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
              {t("acc.result", {
                c: tour.summary.correct, n: tour.summary.n,
                pct: pct(tour.summary.accuracy), rps: tour.summary.rps.toFixed(3),
              })}
            </p>
          )}
          <div className="space-y-2">
            {tour.matches.map((m) => {
              const c = m.compare;
              const winSide = m.predicted === "draw" ? t("common.draw")
                : m.predicted === "home" ? m.home.tla : m.away.tla;
              const g = c?.goals;          // total-goals O/U at the market's Asian line
              const cor = c?.corners;
              return (
                <div key={m.match_id}
                  className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-white/[0.07]">
                  {/* line 1 — teams + real score */}
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Flag crest={m.home.crest} tla={m.home.tla} />
                    {m.home.tla} <b className="tabular-nums">{m.score.home}–{m.score.away}</b> {m.away.tla}
                    <Flag crest={m.away.crest} tla={m.away.tla} />
                  </div>
                  {/* line 2 — per-target verdicts: winner · score · goals O/U · corners O/U */}
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {verdict(t("acc.v_winner"), `${winSide} ${pct(m.probs[m.predicted], 0)}`,
                      m.correct ? "hit" : "miss")}
                    {verdict(t("acc.v_score"), c?.score?.pred ?? "–",
                      c?.score?.hit ? "exact" : null)}
                    {g?.pick && g.hit != null && verdict(
                      `${t("acc.ou_goals")}${g.line ? " " + g.line : ""}`,
                      t(g.pick === "over" ? "acc.over" : "acc.under"),
                      g.hit ? "hit" : "miss",
                      t("acc.v_goals_title", { n: m.score.home + m.score.away }))}
                    {cor?.pick && cor.hit != null && verdict(
                      `${t("acc.ou_corners")}${cor.line ? " " + cor.line : ""}`,
                      t(cor.pick === "over" ? "acc.over" : "acc.under"),
                      cor.hit ? "hit" : "miss",
                      cor.actual_total != null
                        ? t("acc.v_corners_title", { n: cor.actual_total }) : undefined)}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card>
        <h2 className="mb-1 text-lg font-bold">{t("acc.heading")}</h2>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">{t("acc.note")}</p>
        {metrics && (
          <>
            <p className="mb-2 text-sm font-medium">
              {t("acc.backtest", { n: Object.values(metrics)[0]?.n ?? "?" })}
            </p>
            <div className="overflow-x-auto"><table className="w-full max-w-xl min-w-[420px] text-sm tabular-nums">
              <thead>
                <tr className="text-left text-[11px] uppercase text-slate-400">
                  <th className="py-1">{t("acc.model")}</th>
                  <th>{t("acc.rps")}</th><th>{t("acc.logloss")}</th><th>{t("acc.accuracy")}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics).map(([name, m]) => (
                  <tr key={name}
                      className={`border-t border-slate-100 dark:border-white/10 ${
                        name === "ENSEMBLE" ? "font-bold text-emerald-600 dark:text-emerald-400" : ""}`}>
                    <td className="py-1">{name}</td>
                    <td>{m.rps.toFixed(4)}</td>
                    <td>{m.logloss.toFixed(4)}</td>
                    <td>{(m.acc * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </>
        )}
        {status?.report?.scoreline && status?.report?.markets && (
          <div className="mt-4">
            <p className="mb-2 text-sm font-medium">{t("acc.targets")}</p>
            <table className="w-full max-w-xl text-sm tabular-nums">
              <thead>
                <tr className="text-left text-[11px] uppercase text-slate-400">
                  <th className="py-1">{t("acc.t_target")}</th>
                  <th>{t("acc.t_base")}</th>
                  <th>{t("acc.t_model")}</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-slate-100 dark:border-white/10">
                  <td className="py-1">{t("acc.t_score")}</td>
                  <td>{(status.report.scoreline.poisson.top1_hit * 100).toFixed(2)}%</td>
                  <td className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {(status.report.scoreline.dixon_coles.top1_hit * 100).toFixed(2)}%
                  </td>
                </tr>
                {(["over25", "btts"] as const).map((k) => {
                  const m = status.report!.markets![k] as any;
                  if (!m) return null;
                  return (
                    <tr key={k} className="border-t border-slate-100 dark:border-white/10">
                      <td className="py-1">{t(k === "over25" ? "acc.t_ou" : "acc.t_btts")}</td>
                      <td>{(m["derived(matrix+tau)"].acc * 100).toFixed(1)}%</td>
                      <td className="font-semibold text-emerald-600 dark:text-emerald-400">
                        {(m["BLEND"].acc * 100).toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
                <tr className="border-t border-slate-100 dark:border-white/10">
                  <td className="py-1">{t("acc.t_corners")}</td>
                  <td colSpan={2} className="text-xs text-slate-400">{t("acc.t_corners_note")}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
        {status && (
          <p className="mt-2 text-xs text-slate-400">
            {t("acc.last_retrain", {
              d: status.last_retrain ?? t("acc.never"),
              n: status.online_updates_applied,
            })}
          </p>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <div className="flex gap-1">
            {(["team", "h2h"] as const).map((m) => (
              <button key={m} onClick={() => { setMode(m); setResult(null); }}
                className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                  mode === m ? "bg-emerald-600 text-white"
                    : "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>
                {t(m === "team" ? "acc.check_team" : "acc.check_h2h")}
              </button>
            ))}
          </div>
          <select value={team1} onChange={(e) => setTeam1(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800">
            {tlas.map((x) => <option key={x.tla} value={x.tla}>{x.name}</option>)}
          </select>
          {mode === "h2h" && (
            <select value={team2} onChange={(e) => setTeam2(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800">
              {tlas.map((x) => <option key={x.tla} value={x.tla}>{x.name}</option>)}
            </select>
          )}
          <button onClick={check} disabled={loading || (mode === "h2h" && team1 === team2)}
            className="rounded-xl bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-40">
            {loading ? t("common.loading") : t("acc.load")}
          </button>
        </div>

        {result && (result.summary ? (
          <>
            <p className="mb-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
              {t("acc.result", {
                c: result.matches.filter((m) => m.correct).length,
                n: result.summary.n,
                pct: pct(result.summary.accuracy),
                rps: result.summary.rps.toFixed(3),
              })}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase text-slate-400">
                    <th className="py-1">{t("common.date")}</th>
                    <th>{t("common.match")}</th>
                    <th>{t("common.predicted")}</th>
                    <th>{t("common.actual")}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {result.matches.map((m, i) => (
                    <tr key={i} className="border-t border-slate-100 dark:border-white/10">
                      <td className="py-1.5 text-xs text-slate-400">{m.date}</td>
                      <td>
                        {m.home} <b>{m.score}</b> {m.away}
                        <span className="ml-1 text-[10px] text-slate-400">{m.tournament}</span>
                      </td>
                      <td className="text-xs">
                        {m.predicted} ({pct(m.probs[m.predicted], 0)})
                      </td>
                      <td className="text-xs">{m.actual}</td>
                      <td>{m.correct
                        ? <span className="font-bold text-emerald-500">✓</span>
                        : <span className="font-bold text-red-400">✗</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-400">{t("acc.no_data")}</p>
        ))}
      </Card>
    </div>
  );
}
