import { motion } from "framer-motion";
import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`rounded-2xl border border-slate-200/80 bg-white/85 p-4 shadow-sm backdrop-blur-md transition-shadow duration-300 hover:shadow-lg hover:shadow-emerald-500/10 dark:border-white/10 dark:bg-white/[0.045] dark:shadow-black/30 ${className}`}
    >
      {children}
    </motion.div>
  );
}

export function ProbBar({ p, color = "bg-emerald-500", label }: { p: number; color?: string; label?: string }) {
  return (
    <div className="flex items-center gap-2">
      {label && <span className="w-16 shrink-0 text-xs text-slate-500 dark:text-slate-400">{label}</span>}
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, p * 100)}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className={`h-full rounded-full ${color} shadow-[0_0_10px] shadow-current/50`}
        />
      </div>
      <span className="w-12 shrink-0 text-right text-xs font-semibold tabular-nums">
        {(p * 100).toFixed(1)}%
      </span>
    </div>
  );
}

export function Flag({ crest, tla, size = 20 }: { crest?: string | null; tla?: string | null; size?: number }) {
  if (!crest) {
    return (
      <span
        className="inline-flex items-center justify-center rounded bg-slate-300 text-[9px] font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-300"
        style={{ width: size, height: size * 0.75 }}
      >
        {tla ?? "?"}
      </span>
    );
  }
  return <img src={crest} alt={tla ?? ""} width={size} className="inline-block rounded-sm" loading="lazy" />;
}

export function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`} />;
}

// Official FIFA draw-pot (seeding tier) badge: P1 gold ... P4 slate.
const POT_STYLE: Record<number, string> = {
  1: "bg-amber-400/90 text-amber-950",
  2: "bg-sky-400/80 text-sky-950",
  3: "bg-emerald-400/70 text-emerald-950",
  4: "bg-slate-300 text-slate-700 dark:bg-slate-600 dark:text-slate-200",
};

export function PotBadge({ pot, title }: { pot: number; title?: string }) {
  return (
    <span
      title={title ?? `Pot ${pot}`}
      className={`inline-flex items-center rounded px-1 py-px text-[9px] font-bold leading-tight ${POT_STYLE[pot] ?? POT_STYLE[4]}`}
    >
      P{pot}
    </span>
  );
}
