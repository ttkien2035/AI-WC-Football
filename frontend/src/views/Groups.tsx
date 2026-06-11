import { useEffect, useState } from "react";
import { api, type TeamRow, pct } from "../api";
import { Card, Flag, ProbBar } from "../components/ui";
import { useT } from "../i18n";

export default function Groups() {
  const t = useT();
  const [groups, setGroups] = useState<Record<string, TeamRow[]> | null>(null);
  const [meta, setMeta] = useState<{ runs: number; computed_at: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.groups().then((d) => { setGroups(d.groups); setMeta(d.sim_meta); }).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="text-red-500">{t("groups.failed")}{err}</p>;
  if (!groups) return <Skeleton />;

  return (
    <div>
      {meta && (
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          {t("groups.note", {
            runs: meta.runs.toLocaleString(),
            time: new Date(meta.computed_at).toLocaleString(),
          })}
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(groups).map(([g, rows]) => (
          <Card key={g}>
            <h3 className="mb-2 text-sm font-bold tracking-wide text-emerald-600 dark:text-emerald-400">
              {t("groups.group")} {g}
            </h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase text-slate-400">
                  <th className="pb-1">{t("groups.team")}</th>
                  <th className="pb-1 text-center">P</th>
                  <th className="pb-1 text-center">GD</th>
                  <th className="pb-1 text-center">Pts</th>
                  <th className="pb-1 text-right">{t("groups.adv")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.tla} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5">
                      <span className="flex items-center gap-2">
                        <span className="w-4 text-xs text-slate-400">{r.position}</span>
                        <Flag crest={r.crest} tla={r.tla} />
                        <span className="font-medium">{r.name}</span>
                      </span>
                    </td>
                    <td className="text-center tabular-nums">{r.played}</td>
                    <td className="text-center tabular-nums">{r.gd > 0 ? `+${r.gd}` : r.gd}</td>
                    <td className="text-center font-bold tabular-nums">{r.points}</td>
                    <td className="text-right text-xs font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
                      {pct(r.sim?.r32)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 space-y-1.5">
              {rows.map((r) => (
                <ProbBar key={r.tla} label={r.tla} p={r.sim?.r32 ?? 0} />
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="h-56 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />
      ))}
    </div>
  );
}
