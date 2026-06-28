import { useEffect, useState } from "react";
import { api, type BracketEntry, type Match, type Prediction, pct } from "../api";
import { Card, Flag } from "../components/ui";
import { useLang, useT } from "../i18n";

type BracketData = Awaited<ReturnType<typeof api.bracket>>;

const ROUNDS: { key: string; nos: number[] }[] = [
  { key: "bracket.r32", nos: [73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88] },
  { key: "bracket.r16", nos: [89, 90, 91, 92, 93, 94, 95, 96] },
  { key: "bracket.qf", nos: [97, 98, 99, 100] },
  { key: "bracket.sf", nos: [101, 102] },
  { key: "bracket.final", nos: [104] },
];

// knockout stages in order, mapped to the bracket round i18n labels
const KO_STAGES: { stage: string; key: string }[] = [
  { stage: "LAST_32", key: "bracket.r32" },
  { stage: "LAST_16", key: "bracket.r16" },
  { stage: "QUARTER_FINALS", key: "bracket.qf" },
  { stage: "SEMI_FINALS", key: "bracket.sf" },
  { stage: "THIRD_PLACE", key: "bracket.third" },
  { stage: "FINAL", key: "bracket.final" },
];

function slotLabel(routing: BracketData["routing"], no: number): string {
  for (const stage of Object.values(routing)) {
    const pair = stage[no];
    if (pair) {
      const fmt = (s: string | number) =>
        typeof s === "string" && s.startsWith("3:") ? `3rd(${s.slice(2)})` :
        typeof s === "number" ? `W${s}` : String(s);
      return `${fmt(pair[0])} vs ${fmt(pair[1])}`;
    }
  }
  return "";
}

// ── a single real knockout fixture: teams, date, result, expandable prediction
function KnockoutFixture({ m }: { m: Match }) {
  const t = useT();
  const { lang } = useLang();
  const [open, setOpen] = useState(false);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(false);

  const h = m.home.tla, a = m.away.tla;
  const known = !!(h && a);
  const finished = m.status === "FINISHED" && m.score.home != null;
  const date = new Date(m.utcDate).toLocaleString(lang === "vi" ? "vi-VN" : "en-US",
    { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  const toggle = async () => {
    if (!known || finished) return;
    const next = !open;
    setOpen(next);
    if (next && !pred) {
      setLoading(true);
      try { setPred(await api.predict(h!, a!)); } finally { setLoading(false); }
    }
  };

  const side = (tla: string | null, p?: number, win?: boolean) => (
    <span className={`flex items-center gap-1.5 ${win ? "font-bold" : ""}`}>
      <Flag crest={tla === h ? m.home.crest : m.away.crest} tla={tla} size={16} />
      {tla ?? t("bracket.tbd")}{p != null && <span className="text-slate-400">{p}</span>}
    </span>
  );

  return (
    <div className={`rounded-xl border p-2.5 text-sm ${known && !finished
      ? "cursor-pointer border-slate-200/80 bg-white/85 hover:border-emerald-400 dark:border-white/10 dark:bg-white/[0.05]"
      : "border-slate-200/80 bg-slate-100/70 dark:border-white/10 dark:bg-white/[0.04]"}`}
      onClick={toggle}>
      <div className="mb-1 flex items-center justify-between text-[10px] text-slate-400">
        <span>📅 {date}</span>
        <span>{finished ? t("bracket.ft") : known ? t("bracket.tap") : ""}</span>
      </div>
      <div className="flex items-center justify-between gap-2 font-semibold">
        {side(h, undefined, finished && (m.score.winner === "HOME_TEAM"))}
        {finished
          ? <b className="tabular-nums">{m.score.home}–{m.score.away}</b>
          : <span className="text-slate-400">vs</span>}
        {side(a, undefined, finished && (m.score.winner === "AWAY_TEAM"))}
      </div>

      {open && known && !finished && (
        <div className="mt-2 border-t border-slate-200/70 pt-2 text-xs dark:border-white/10"
          onClick={(e) => e.stopPropagation()}>
          {loading || !pred ? (
            <p className="text-slate-400">…</p>
          ) : (
            <div className="space-y-1.5">
              <div className="flex justify-between tabular-nums">
                <span>{h} <b>{pct(pred.probs.home, 0)}</b></span>
                <span className="text-slate-400">{t("match.draw")} {pct(pred.probs.draw, 0)}</span>
                <span><b>{pct(pred.probs.away, 0)}</b> {a}</span>
              </div>
              <div className="flex flex-wrap gap-1.5 text-[11px]">
                {pred.win_confidence && (
                  <span className="rounded-full bg-slate-200/70 px-2 py-0.5 dark:bg-white/10">
                    {t("bracket.win_pick")}: <b>{pred.probs.home >= pred.probs.away ? h : a}</b>
                    {" · "}{t(`conf.${pred.win_confidence}`)}
                  </span>
                )}
                {pred.scorelines?.[0] && (
                  <span className="rounded-full bg-slate-200/70 px-2 py-0.5 dark:bg-white/10">
                    {t("acc.v_score")} <b>{pred.scorelines[0].home}-{pred.scorelines[0].away}</b>
                  </span>
                )}
                {pred.market_lines?.goals && (
                  <span className="rounded-full bg-slate-200/70 px-2 py-0.5 dark:bg-white/10">
                    {t("acc.ou_goals")} {pred.market_lines.goals.line} ·{" "}
                    <b>{t(pred.market_lines.goals.pick === "over" ? "acc.over" : "acc.under")}</b>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MatchCard({ no, entry, label, when }: {
  no: number; entry?: BracketEntry; label: string;
  when?: { date: string; city: string };
}) {
  const { lang } = useLang();
  const top = entry?.winner_top?.slice(0, 3) ?? [];
  const h = entry?.home_top?.[0];
  const a = entry?.away_top?.[0];
  const dateStr = when
    ? new Date(when.date + "T12:00:00Z").toLocaleDateString(
        lang === "vi" ? "vi-VN" : "en-US", { day: "numeric", month: "short" })
    : null;
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white/85 p-2.5 text-xs shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/[0.045]">
      <div className="mb-1 flex justify-between text-[10px] text-slate-400">
        <span>M{no}</span>
        <span>{label}</span>
      </div>
      {when && (
        <div className="mb-1 text-[10px] font-medium text-sky-600 dark:text-sky-400">
          📅 {dateStr} · {when.city}
        </div>
      )}
      <div className="mb-1.5 flex items-center justify-between font-semibold">
        <span>{h ? `${h.tla} ${pct(h.p, 0)}` : "TBD"}</span>
        <span className="text-slate-400">vs</span>
        <span>{a ? `${a.tla} ${pct(a.p, 0)}` : "TBD"}</span>
      </div>
      <div className="flex gap-1">
        {top.map((w) => (
          <span
            key={w.tla}
            className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
            title={`Most likely winner: ${w.tla} ${pct(w.p)}`}
          >
            {w.tla} {pct(w.p, 0)}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Bracket() {
  const t = useT();
  const [data, setData] = useState<BracketData | null>(null);

  useEffect(() => {
    api.bracket().then(setData);
  }, []);

  if (!data) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200/80 dark:bg-white/[0.1]" />;

  const koRounds = KO_STAGES
    .map((r) => ({ ...r, ms: (data.real?.[r.stage] ?? []).slice() }))
    .filter((r) => r.ms.length);

  return (
    <div className="space-y-4">
      {/* real knockout fixtures + results + tap-to-predict */}
      {koRounds.length > 0 && (
        <Card>
          <h2 className="text-base font-bold">{t("bracket.ko_heading")}</h2>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">{t("bracket.ko_note")}</p>
          <div className="space-y-4">
            {koRounds.map((r) => (
              <div key={r.stage}>
                <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wider text-slate-400">{t(r.key)}</h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  {r.ms
                    .sort((m1, m2) => m1.utcDate.localeCompare(m2.utcDate))
                    .map((m) => <KnockoutFixture key={m.id} m={m} />)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* projected bracket from the tournament simulation */}
      <Card className="overflow-x-auto">
        <h2 className="mb-1 text-base font-bold">{t("bracket.proj_heading")}</h2>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          {t("bracket.note", { runs: data.meta.runs.toLocaleString() })}
        </p>
        <div className="flex min-w-[1100px] gap-4">
          {ROUNDS.map((round) => (
            <div key={round.key} className="flex flex-1 flex-col">
              <h3 className="mb-2 text-center text-xs font-bold uppercase tracking-wider text-slate-400">
                {t(round.key)}
              </h3>
              <div className="flex flex-1 flex-col justify-around gap-2">
                {round.nos.map((no) => (
                  <MatchCard key={no} no={no} entry={data.sim?.[no]}
                    label={slotLabel(data.routing, no)}
                    when={data.schedule?.[no]} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
