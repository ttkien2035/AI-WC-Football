import { useEffect, useState } from "react";
import { api, type OddsRow } from "../api";
import { Card, Flag } from "../components/ui";
import { useT } from "../i18n";

const fmt = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

export default function Odds() {
  const t = useT();
  const [data, setData] = useState<Awaited<ReturnType<typeof api.odds>> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.odds().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="text-red-500">Failed: {err}</p>;
  if (!data) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />;

  const noMarket = data.source === "disabled";

  return (
    <div className="space-y-4">
      {noMarket && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
          {t("odds.no_key")}
        </div>
      )}
      {data.quota && (
        <p className="text-xs text-slate-400">{t("odds.quota", { n: data.quota.remaining })}</p>
      )}
      <details className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm dark:border-sky-900 dark:bg-sky-950/40">
        <summary className="cursor-pointer font-semibold text-sky-700 dark:text-sky-300">
          {t("odds.legend_title")}
        </summary>
        <div className="mt-2 whitespace-pre-line text-xs leading-5 text-slate-600 dark:text-slate-300">
          {t("odds.legend")}
        </div>
      </details>
      {data.matches.map((r) => (
        <Card key={r.match_id}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-semibold">
              <Flag crest={r.home.crest} tla={r.home.tla} />
              {r.home.name} <span className="text-slate-400">vs</span> {r.away.name}
              <Flag crest={r.away.crest} tla={r.away.tla} />
            </div>
            <span className="text-xs text-slate-400">
              {new Date(r.utcDate).toLocaleString()} · {r.group ?? r.stage}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm tabular-nums">
              <thead>
                <tr className="text-left text-[11px] uppercase text-slate-400">
                  <th className="py-1 pr-2">{t("odds.bet")}</th>
                  <th>1 ({r.home.tla})</th><th>X</th><th>2 ({r.away.tla})</th>
                  <th>{t("odds.ou")}</th><th>{t("odds.ah")}</th><th>{t("odds.corners")}</th>
                </tr>
              </thead>
              <tbody>
                {r.market?.h2h && (() => {
                  const mh = r.market!.h2h!;
                  const vals = [mh.home, mh.draw, mh.away].filter((x): x is number => x != null);
                  const fav = vals.length ? Math.min(...vals) : null;
                  const cell = (v: number | null | undefined, valKey: string) => (
                    <td className={
                      r.value?.[valKey] ? "font-bold text-emerald-500"
                        : v != null && v === fav ? "font-bold text-sky-500" : ""}>
                      {fmt(v)}{v != null && v === fav && (
                        <span className="ml-1 rounded bg-sky-100 px-1 text-[9px] text-sky-700 dark:bg-sky-950 dark:text-sky-300">
                          {t("odds.fav")}
                        </span>
                      )}
                    </td>
                  );
                  return (
                    <tr className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1.5 pr-2 font-medium">{t("odds.market")}</td>
                      {cell(mh.home, "home")}{cell(mh.draw, "draw")}{cell(mh.away, "away")}
                      <td>
                        {r.market!.totals
                          ? `${r.market!.totals.point} → O ${fmt(r.market!.totals.over)} / U ${fmt(r.market!.totals.under)}`
                          : "–"}
                      </td>
                      <td>
                        {r.market!.spreads
                          ? `${r.home.tla} ${r.market!.spreads.point > 0 ? "+" : ""}${r.market!.spreads.point} → ${fmt(r.market!.spreads.home)}/${fmt(r.market!.spreads.away)}`
                          : "–"}
                      </td>
                      <td>
                        {r.market!.corners_totals?.length
                          ? r.market!.corners_totals.slice(0, 2).map((c) =>
                              `${c.point}: ${fmt(c.over)}/${fmt(c.under)}`).join("  ")
                          : "–"}
                      </td>
                    </tr>
                  );
                })()}
                <tr className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-2 font-medium text-sky-600 dark:text-sky-400">
                    {t("odds.model")}
                  </td>
                  {(["home", "draw", "away"] as const).map((k) => (
                    <td key={k}>
                      {fmt(r.fair.h2h[k])}
                      <span className="ml-1 text-[10px] text-slate-400">
                        {(r.fair.probs[k] * 100).toFixed(0)}%
                      </span>
                    </td>
                  ))}
                  <td>O {fmt(r.fair.over25)} / U {fmt(r.fair.under25)}</td>
                  <td className="text-slate-400">—</td>
                  <td>~{r.fair.expected_corners.toFixed(1)} · O9.5 {fmt(r.fair.corners_over_95)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {r.value && Object.keys(r.value).length > 0 && (
            <p className="mt-1 text-xs font-medium text-emerald-500">
              ⚡ {t("odds.value", {
                v: Object.entries(r.value).map(([k, v]) => `${k} +${(v * 100).toFixed(1)}pt`).join(", "),
              })}
            </p>
          )}
        </Card>
      ))}
      <p className="text-center text-[11px] text-slate-400">
        {t("odds.footer", { ml: data.ml ? "✓" : "✗" })}
      </p>
    </div>
  );
}
