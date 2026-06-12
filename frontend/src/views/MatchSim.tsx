import { useEffect, useMemo, useState } from "react";
import { Radio } from "lucide-react";
import { api, type Analysis, type EvalResult, type Match, type Prediction, type TeamRow, pct } from "../api";
import { Card, Flag, ProbBar } from "../components/ui";
import { useLang, useT, outcomeLabel } from "../i18n";
import { track } from "../track";

export default function MatchSim() {
  const t = useT();
  const [teams, setTeams] = useState<Record<string, TeamRow>>({});
  const [live, setLive] = useState<Match[]>([]);
  const [upcoming, setUpcoming] = useState<Match[]>([]);
  const [home, setHome] = useState("MEX");
  const [away, setAway] = useState("RSA");
  const [inPlay, setInPlay] = useState(false);
  const [minute, setMinute] = useState(45);
  const [hg, setHg] = useState(0);
  const [ag, setAg] = useState(0);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [h2h, setH2h] = useState<EvalResult | null>(null);
  const [ana, setAna] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.teams().then(setTeams);
    api.live().then((d) => {
      setLive(d.live);
      // default pair = the live match (most relevant right now)
      const lm = d.live[0];
      if (lm?.home.tla && lm.away.tla) {
        setHome(lm.home.tla);
        setAway(lm.away.tla);
      }
    });
    api.matches().then((d) => {
      const next = d.matches
        .filter((m) => (m.status === "TIMED" || m.status === "SCHEDULED")
          && m.home.tla && m.away.tla)
        .sort((x, y) => x.utcDate.localeCompare(y.utcDate))
        .slice(0, 6);
      setUpcoming(next);
      // no live match -> default to the next kickoff
      const up = next[0];
      setHome((cur) => (cur === "MEX" && up?.home.tla ? up.home.tla : cur));
      setAway((cur) => (cur === "RSA" && up?.away.tla ? up.away.tla : cur));
    });
  }, []);

  const tlas = useMemo(
    () => Object.values(teams).sort((a, b) => a.name.localeCompare(b.name)),
    [teams],
  );

  const run = async (h: string = home, a: string = away, useInPlay: boolean = inPlay) => {
    setLoading(true);
    setErr(null);
    setH2h(null);
    setAna(null);
    try {
      track("predict", { pair: `${h}-${a}`, inplay: useInPlay ? "1" : "0" });
      const params = useInPlay ? `?minute=${minute}&hg=${hg}&ag=${ag}` : "";
      setPred(await api.predict(h, a, params));
      api.evalH2h(h, a).then(setH2h).catch(() => {});
      api.analysis(h, a).then(setAna).catch(() => {});
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  const pickMatch = (m: Match) => {
    if (m.home.tla && m.away.tla) {
      setHome(m.home.tla);
      setAway(m.away.tla);
      setInPlay(false);
      run(m.home.tla, m.away.tla, false);   // predict immediately
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <Card>
        <h2 className="mb-3 text-base font-bold">{t("match.setup")}</h2>
        {live.length > 0 && (
          <div className="mb-3">
            <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-red-500">
              <Radio size={12} className="animate-pulse" /> {t("match.live_now")}
            </p>
            {live.map((m) => (
              <button key={m.id} onClick={() => pickMatch(m)}
                className="mb-1 w-full rounded-lg bg-red-50 px-2 py-1.5 text-left text-xs hover:bg-red-100 dark:bg-red-950/40 dark:hover:bg-red-900/40">
                {m.home.tla} {m.score.home ?? 0}–{m.score.away ?? 0} {m.away.tla}
                {m.minute_estimate != null && ` · ~${m.minute_estimate}'`}
              </button>
            ))}
          </div>
        )}
        {upcoming.length > 0 && (
          <div className="mb-3">
            <p className="mb-1 text-xs font-semibold text-slate-400">{t("match.upcoming")}</p>
            <div className="space-y-1">
              {upcoming.map((m) => (
                <button key={m.id} onClick={() => pickMatch(m)}
                  className="flex w-full items-center justify-between rounded-lg bg-slate-100/80 px-2 py-1.5 text-left text-xs transition hover:bg-emerald-50 hover:ring-1 hover:ring-emerald-400 dark:bg-white/[0.07] dark:hover:bg-emerald-950/40">
                  <span className="flex items-center gap-1.5 font-medium">
                    <Flag crest={m.home.crest} tla={m.home.tla} size={14} /> {m.home.tla}
                    <span className="text-slate-400">vs</span>
                    {m.away.tla} <Flag crest={m.away.crest} tla={m.away.tla} size={14} />
                  </span>
                  <span className="tabular-nums text-slate-400">
                    {new Date(m.utcDate).toLocaleString([], {
                      day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="space-y-3">
          <Select label={t("match.home")} value={home} onChange={setHome} teams={tlas} />
          <Select label={t("match.away")} value={away} onChange={setAway} teams={tlas} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={inPlay} onChange={(e) => setInPlay(e.target.checked)} />
            {t("match.inplay")}
          </label>
          {inPlay && (
            <div className="grid grid-cols-3 gap-2">
              <NumInput label={t("match.minute")} value={minute} setValue={setMinute} max={120} />
              <NumInput label={`${home} (${t("match.goals")})`} value={hg} setValue={setHg} max={20} />
              <NumInput label={`${away} (${t("match.goals")})`} value={ag} setValue={setAg} max={20} />
            </div>
          )}
          <button onClick={() => run()} disabled={loading || home === away}
            className="w-full rounded-xl bg-emerald-600 py-2.5 font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-40">
            {loading ? t("match.simulating") : t("match.predict")}
          </button>
          {home === away && <p className="text-xs text-amber-500">{t("match.pick_two")}</p>}
          {err && <p className="text-xs text-red-500">{err}</p>}
        </div>
      </Card>

      <Card>
        {!pred ? (
          <p className="py-20 text-center text-sm text-slate-400">
            {t("match.empty")} <b>{t("match.predict")}</b>.
          </p>
        ) : (
          <ResultPanel pred={pred} teams={teams} h2h={h2h} ana={ana} />
        )}
      </Card>
    </div>
  );
}

function ResultPanel({ pred, teams, h2h, ana }: {
  pred: Prediction; teams: Record<string, TeamRow>; h2h: EvalResult | null;
  ana: Analysis | null;
}) {
  const t = useT();
  const h = teams[pred.home];
  const a = teams[pred.away];
  const c = pred.components;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-center gap-2 text-base font-bold sm:gap-4 sm:text-lg">
        <span className="flex items-center gap-2">
          <Flag crest={h?.crest} tla={pred.home} size={28} /> {h?.name ?? pred.home}
        </span>
        {pred.in_play && pred.score ? (
          <span className="rounded-lg bg-red-100 px-3 py-1 text-red-600 dark:bg-red-950 dark:text-red-300">
            {pred.score.home}–{pred.score.away} <span className="text-xs">~{pred.minute}'</span>
          </span>
        ) : (
          <span className="text-slate-400">vs</span>
        )}
        <span className="flex items-center gap-2">
          {a?.name ?? pred.away} <Flag crest={a?.crest} tla={pred.away} size={28} />
        </span>
      </div>

      <div className="mb-4 space-y-2">
        <ProbBar label={`${pred.home} ${t("match.win")}`} p={pred.probs.home} color="bg-emerald-500" />
        <ProbBar label={t("match.draw")} p={pred.probs.draw} color="bg-slate-400" />
        <ProbBar label={`${pred.away} ${t("match.win")}`} p={pred.probs.away} color="bg-sky-500" />
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat title={`xG ${pred.home}`} value={String(pred.lambdas.home_remaining ?? pred.lambdas.home)} />
        <Stat title={`xG ${pred.away}`} value={String(pred.lambdas.away_remaining ?? pred.lambdas.away)} />
        <Stat title={t("match.over25")} value={pct(pred.over25)} />
        <Stat title={t("match.btts")} value={pct(pred.btts)} />
      </div>

      <h3 className="mb-1 text-sm font-semibold">{t("match.scorelines")}</h3>
      <div className="mb-4 flex flex-wrap gap-2">
        {pred.scorelines.map((s, i) => (
          <span key={i}
            className={`rounded-lg px-2.5 py-1 text-sm font-semibold tabular-nums ${
              i === 0 ? "bg-emerald-600 text-white" : "bg-slate-200/80 dark:bg-white/[0.1]"}`}>
            {s.home}–{s.away} <span className="text-xs opacity-75">{pct(s.p)}</span>
          </span>
        ))}
      </div>

      {pred.components.context?.notes?.length ? <ContextBanner pred={pred} /> : null}
      {pred.market_lines && <AsianLinePanel pred={pred} />}
      {ana && <AnalysisPanel ana={ana} />}
      {pred.halves && <HalvesPanel pred={pred} />}
      {pred.corners && <CornersPanel pred={pred} />}
      {pred.knockout && <KnockoutPanel pred={pred} />}
      {pred.simulation && <SimPanel pred={pred} />}
      {h2h && <H2hPanel pred={pred} h2h={h2h} />}

      <h3 className="mb-1 text-sm font-semibold">{t("match.components")}</h3>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-slate-400">
            <th className="py-1">{t("match.source")}</th>
            <th>{t("match.weight")}</th>
            <th>{pred.home}</th><th>{t("match.draw")}</th><th>{pred.away}</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {c.ml && <CompRow name={t("match.ml_row")} w={c.weights.ml} v={c.ml} />}
          <CompRow name={t("match.poisson_row")} w={c.weights.poisson} v={c.poisson} />
          <CompRow name={t("match.elo_row")} w={c.weights.elo} v={c.elo} />
          {c.market && <CompRow name={t("match.market_row")} w={c.weights.market} v={c.market} />}
        </tbody>
      </table>
      {!c.market && !pred.in_play && (
        <p className="mt-2 text-[11px] text-slate-400">{t("match.no_market")}</p>
      )}
      <p className="mt-2 text-[11px] text-slate-400">
        Elo: {pred.elo.home.toFixed(0)} vs {pred.elo.away.toFixed(0)} ({pct(pred.elo.expectancy)})
      </p>
    </div>
  );
}

function HalvesPanel({ pred }: { pred: Prediction }) {
  const t = useT();
  const { lang } = useLang();
  const h = pred.halves!;
  const chips = (scores?: { home: number; away: number; p: number }[]) =>
    (scores ?? []).map((s, i) => (
      <span key={i} className="rounded bg-slate-200/80 px-1.5 py-0.5 text-xs font-semibold tabular-nums dark:bg-white/[0.1]">
        {s.home}–{s.away} <span className="opacity-70">{pct(s.p, 0)}</span>
      </span>
    ));
  const htft = h.htft ? Object.entries(h.htft).sort((x, y) => y[1] - x[1]).slice(0, 5) : null;
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">{t("match.halves")}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {(["h1", "h2"] as const).map((key) => {
          const half = h[key];
          return (
            <div key={key} className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-white/[0.07]">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">
                {t(`match.${key}`)} {half?.note && `(${half.note})`}
              </p>
              {half?.probs && (
                <p className="mb-1 text-xs tabular-nums">
                  {pred.home} {pct(half.probs.home)} · {t("match.draw")} {pct(half.probs.draw)} · {pred.away} {pct(half.probs.away)}
                </p>
              )}
              <div className="flex flex-wrap gap-1">{chips(half?.top_scores)}</div>
            </div>
          );
        })}
      </div>
      {htft && (
        <div className="mt-2">
          <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">{t("match.htft")}</p>
          <div className="flex flex-wrap gap-1">
            {htft.map(([k, v]) => {
              const [x, y] = k.split("/");
              return (
                <span key={k} className="rounded-lg bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
                  {outcomeLabel(x, pred.home, pred.away, lang)}/{outcomeLabel(y, pred.home, pred.away, lang)} {pct(v)}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function CornersPanel({ pred }: { pred: Prediction }) {
  const t = useT();
  const c = pred.corners!;
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">{t("match.corners")}</h3>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <Stat title={pred.home} value={c.expected.home.toFixed(1)} />
        <Stat title={pred.away} value={c.expected.away.toFixed(1)} />
        <Stat title={t("match.corners_total")} value={c.expected.total.toFixed(1)} />
        <Stat title={t("match.h1")} value={c.expected.h1.toFixed(1)} />
        <Stat title={t("match.h2")} value={c.expected.h2.toFixed(1)} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1 text-xs">
        {Object.entries(c.over).map(([k, v]) => (
          <span key={k} className="rounded bg-slate-200 px-1.5 py-0.5 tabular-nums dark:bg-white/[0.07]">
            {k.replace("h1_", `${t("match.h1")} O`).replace("ft_", "FT O")}: {pct(v)}
          </span>
        ))}
      </div>
      {c.in_play && (
        <p className="mt-1 text-xs text-slate-400">
          {t("match.corners_sofar", {
            h: c.in_play.so_far?.home ?? "?",
            a: c.in_play.so_far?.away ?? "?",
            t: c.in_play.projected_total,
          })}
        </p>
      )}
    </div>
  );
}

function KnockoutPanel({ pred }: { pred: Prediction }) {
  const t = useT();
  const k = pred.knockout!;
  const via = (side: "home" | "away") => k.win_via[side];
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">
        {t("match.ko")} {pred.stage === "GROUP_STAGE" && t("match.ko_if")}
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat title={t("match.ko_90")} value={pct(1 - k.p_extra_time)} />
        <Stat title={t("match.ko_et")} value={pct(k.p_extra_time)} />
        <Stat title={t("match.ko_pens")} value={pct(k.p_penalties)} />
        <Stat title={t("match.ko_pen_win", { team: pred.home })} value={pct(k.pens_win.home)} />
      </div>
      <div className="mt-2 space-y-1.5">
        <ProbBar label={t("match.advance", { team: pred.home })} p={k.advance.home} color="bg-emerald-500" />
        <ProbBar label={t("match.advance", { team: pred.away })} p={k.advance.away} color="bg-sky-500" />
      </div>
      <p className="mt-1 text-[11px] tabular-nums text-slate-400">
        {t("match.via", { team: pred.home, a: pct(via("home").regulation), b: pct(via("home").extra_time), c: pct(via("home").penalties) })}
        {" — "}
        {t("match.via", { team: pred.away, a: pct(via("away").regulation), b: pct(via("away").extra_time), c: pct(via("away").penalties) })}
      </p>
    </div>
  );
}

function ContextBanner({ pred }: { pred: Prediction }) {
  const t = useT();
  const c = pred.components.context!;
  const stakeWord = (s?: string) => s ? t(`ctx.stake_${s}`) : "";
  return (
    <div className="mb-4 rounded-xl border border-amber-300/60 bg-amber-50 p-3 dark:border-amber-700/50 dark:bg-amber-950/30">
      <h3 className="mb-1 text-sm font-semibold text-amber-700 dark:text-amber-300">
        🧮 {t("match.context")}
      </h3>
      {c.stakes && (
        <p className="mb-1 text-xs font-medium">
          {pred.home}: <b>{stakeWord(c.stakes.home)}</b> · {pred.away}: <b>{stakeWord(c.stakes.away)}</b>
        </p>
      )}
      {pred.components.venue?.venue && (
        <p className="mb-1 text-[11px] text-slate-500 dark:text-slate-400">
          🏟 {pred.components.venue.venue.stadium}, {pred.components.venue.venue.city}
          {pred.components.venue.venue.alt >= 1000 && ` · ${pred.components.venue.venue.alt}m`}
          {pred.components.venue.venue.roof && " · 🏠"}
        </p>
      )}
      {c.notes.map((n, i) => (
        <p key={i} className="text-xs leading-5 text-slate-600 dark:text-slate-300">• {t(n.key, n.params)}</p>
      ))}
    </div>
  );
}

function AsianLinePanel({ pred }: { pred: Prediction }) {
  const t = useT();
  const ml = pred.market_lines!;
  const Row = ({ label, d }: { label: string; d: typeof ml.goals }) => (
    <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-white/[0.07]">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-1">
        <span className="text-xs font-bold">
          {label}{" "}
          <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-extrabold tabular-nums text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
            {d.line}
          </span>
        </span>
        <span className="text-[10px] text-slate-400">
          {d.source === "market" ? `📊 ${t("match.line_market")}` : t("match.line_default")}
          {d.market && d.market.over != null &&
            ` · ${t("match.mkt_price")}: ${d.market.over?.toFixed(2)}/${d.market.under?.toFixed(2)}`}
        </span>
      </div>
      {d.confidence && (
        <p className="mb-1 text-[11px] font-semibold">
          {d.confidence === "toss_up" ? (
            <span className="text-amber-600 dark:text-amber-400">{t("conf.toss_up")}</span>
          ) : (
            <span className="text-emerald-600 dark:text-emerald-400">
              {t("conf.pick")}: {d.pick === "over" ? t("match.over") : t("match.under")} ({t(`conf.${d.confidence}`)})
            </span>
          )}
        </p>
      )}
      <ProbBar label={t("match.over")} p={d.over} color="bg-orange-500" />
      <div className="h-1" />
      <ProbBar label={t("match.under")} p={d.under} color="bg-teal-500" />
      {d.push > 0.001 && (
        <p className="mt-0.5 text-right text-[10px] text-slate-400">
          {t("match.push")}: {pct(d.push)}
        </p>
      )}
    </div>
  );
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">🎯 {t("match.asian")}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <Row label={t("match.goals_line")} d={ml.goals} />
        <Row label={t("match.corners_line2")} d={ml.corners} />
      </div>
    </div>
  );
}

function AnalysisPanel({ ana }: { ana: Analysis }) {
  const t = useT();
  const sides = [ana.home, ana.away];
  const statusIcon = { in_xi: "✓", missing: "⚠", unknown: "·" } as const;
  const statusColor = {
    in_xi: "text-emerald-500", missing: "text-amber-500", unknown: "text-slate-400",
  } as const;
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">{t("ana.heading")}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {sides.map((tla) => {
          const d = ana.teams[tla];
          if (!d) return null;
          const formation = d.formation_live ?? d.profile.formation;
          return (
            <div key={tla} className="rounded-xl bg-slate-100 p-2.5 text-xs dark:bg-white/[0.07]">
              <p className="mb-1 font-bold">{tla}
                {formation && (
                  <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                    {formation} {d.formation_live && t("ana.live_xi")}
                  </span>
                )}
              </p>
              {d.profile.manager && <p>{t("ana.manager")}: {d.profile.manager}</p>}
              {d.manager_note && (
                <p className="mt-0.5 italic text-slate-500 dark:text-slate-400">🧠 {d.manager_note}</p>
              )}
              {d.profile.style && (
                <p>{t("ana.style")}: {d.profile.style.map((s) => t(`style.${s}`)).join(" · ")}</p>
              )}
              {d.profile.value_tier && (
                <p>{t("ana.value")}: {"★".repeat(d.profile.value_tier)}{"☆".repeat(5 - d.profile.value_tier)}</p>
              )}
              <p className="mt-1 font-semibold">{t("ana.key_players")}:</p>
              {d.key_players.map((kp, i) => (
                <p key={i} className="leading-5">
                  <span className={`font-bold ${statusColor[kp.status]}`}>{statusIcon[kp.status]}</span>{" "}
                  {kp.name} <span className="text-slate-400">({kp.pos} · {t(`ana.${kp.status}`)})</span>
                </p>
              ))}
              {d.absence_elo_penalty < 0 && (
                <p className="mt-1 font-medium text-amber-500">
                  {t("ana.penalty_note", { n: d.absence_elo_penalty })}
                </p>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-1 text-[10px] text-slate-400">{t("ana.style_note")}</p>
    </div>
  );
}

function SimPanel({ pred }: { pred: Prediction }) {
  const t = useT();
  const s = pred.simulation!;
  const sc = s.scenarios;
  const items: [string, number][] = [
    [t("match.sim_late"), sc.late_goal_80plus],
    [t("match.sim_cs_h", { team: pred.home }), sc.clean_sheet_home],
    [t("match.sim_cs_a", { team: pred.away }), sc.clean_sheet_away],
    [t("match.sim_comeback", { team: pred.home }), sc.home_comeback],
    [t("match.sim_blew", { team: pred.home }), sc.home_blew_lead],
  ];
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">🎲 {t("match.sim", { n: s.runs.toLocaleString() })}</h3>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
        {items.map(([label, p], i) => (
          <div key={i} className="rounded-lg bg-slate-100/80 p-2 text-center dark:bg-white/[0.07]">
            <p className="text-base font-bold tabular-nums">{pct(p)}</p>
            <p className="text-[10px] leading-tight text-slate-400">{label}</p>
          </div>
        ))}
      </div>
      <p className="mt-1 text-[10px] text-slate-400">{t("match.sim_note")}</p>
    </div>
  );
}

function H2hPanel({ pred, h2h }: { pred: Prediction; h2h: EvalResult }) {
  const t = useT();
  if (!h2h.summary || h2h.matches.length === 0) {
    return (
      <div className="mb-4">
        <h3 className="mb-1 text-sm font-semibold">{t("match.h2h")}</h3>
        <p className="text-xs text-slate-400">{t("match.h2h_none")}</p>
      </div>
    );
  }
  const correct = h2h.matches.filter((m) => m.correct).length;
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold">{t("match.h2h")}</h3>
      <p className="mb-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
        {t("match.h2h_acc", { c: correct, n: h2h.summary.n, rps: h2h.summary.rps.toFixed(3) })}
      </p>
      <div className="space-y-1">
        {h2h.matches.slice(0, 6).map((m, i) => (
          <p key={i} className="text-xs tabular-nums text-slate-500 dark:text-slate-400">
            {m.correct
              ? <span className="font-bold text-emerald-500">✓</span>
              : <span className="font-bold text-red-400">✗</span>}{" "}
            {m.date} · {m.home} <b>{m.score}</b> {m.away}
            <span className="ml-1 opacity-70">
              ({t("match.pred")} {m.predicted} {pct(m.probs[m.predicted], 0)})
            </span>
          </p>
        ))}
      </div>
    </div>
  );
}

const CompRow = ({ name, w, v }: { name: string; w: number; v: Record<string, number> }) => (
  <tr className="border-t border-slate-100 dark:border-white/10">
    <td className="py-1">{name}</td>
    <td>{(w * 100).toFixed(0)}%</td>
    <td>{pct(v.home)}</td><td>{pct(v.draw)}</td><td>{pct(v.away)}</td>
  </tr>
);

const Stat = ({ title, value }: { title: string; value: string }) => (
  <div className="rounded-xl bg-slate-100 p-2.5 text-center dark:bg-white/[0.07]">
    <p className="text-[10px] uppercase tracking-wide text-slate-400">{title}</p>
    <p className="text-base font-bold tabular-nums">{value}</p>
  </div>
);

function Select({ label, value, onChange, teams }: {
  label: string; value: string; onChange: (v: string) => void; teams: TeamRow[];
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs text-slate-400">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-800">
        {teams.map((x) => (
          <option key={x.tla} value={x.tla}>{x.name} ({x.tla})</option>
        ))}
      </select>
    </label>
  );
}

function NumInput({ label, value, setValue, max }: {
  label: string; value: number; setValue: (n: number) => void; max: number;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[10px] text-slate-400">{label}</span>
      <input type="number" min={0} max={max} value={value}
        onChange={(e) => setValue(Math.max(0, Math.min(max, Number(e.target.value))))}
        className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800" />
    </label>
  );
}
