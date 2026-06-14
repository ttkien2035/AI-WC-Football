"""Generate the experiment figures embedded in docs/METHODOLOGY.md.
All plots are produced from the real fit artifacts / eval data. Headless (Agg).
Run:  python -m ml.make_figures
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "app" / "data" / "models"
FIG = ROOT.parent / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 110, "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True})
EM, SK = "#10b981", "#0ea5e9"      # emerald / sky


def fig_corner_determinants():
    c = json.load(open(MODELS / "corners_fit.json"))["corr"]
    items = sorted(c.items(), key=lambda kv: kv[1])
    k, v = zip(*items)
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(k, v, color=[EM if x >= 0 else "#ef4444" for x in v])
    ax.axvline(0, color="#334155", lw=0.8)
    ax.set_xlabel("Pearson r with corners-for")
    ax.set_title("Fig 1. Corner determinants (628 intl team-matches)")
    for i, x in enumerate(v):
        ax.text(x + (0.01 if x >= 0 else -0.01), i, f"{x:+.2f}",
                va="center", ha="left" if x >= 0 else "right", fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "corner_determinants.png"); plt.close(fig)


def fig_total_dispersion():
    d = pd.read_csv(MODELS / "eval_features.csv"); tot = (d.gh + d.ga).values
    mu = tot.mean()
    from scipy.stats import poisson
    ks = np.arange(0, 8)
    emp = [np.mean(tot == k) for k in ks[:-1]] + [np.mean(tot >= 7)]
    poi = [poisson.pmf(k, mu) for k in ks[:-1]] + [1 - poisson.cdf(6, mu)]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    x = np.arange(len(ks)); w = 0.4
    ax.bar(x - w / 2, emp, w, label="empirical", color=EM)
    ax.bar(x + w / 2, poi, w, label=f"Poisson(μ={mu:.2f})", color=SK)
    ax.set_xticks(x); ax.set_xticklabels([str(k) for k in ks[:-1]] + ["7+"])
    ax.set_xlabel("total goals"); ax.set_ylabel("P")
    ax.set_title(f"Fig 2. Total-goals are over-dispersed (Var/Mean={tot.var()/mu:.2f})")
    ax.legend()
    fig.tight_layout(); fig.savefig(FIG / "total_dispersion.png"); plt.close(fig)


def fig_ou_reliability():
    import sys; sys.path.insert(0, str(ROOT))
    from app.engine import match_model as MM
    d = pd.read_csv(MODELS / "eval_features.csv")
    r = json.load(open(MODELS / "goal_rates.json")); a, b = r["a"], r["b"]
    ed = d.elo_diff.values
    p = np.array([MM.prob_at_line(MM.score_matrix(np.exp(a + b * e / 100),
                  np.exp(a - b * e / 100), rho=-0.06), 2.5)["over"] for e in ed])
    act = (d.gh + d.ga > 2.5).astype(float).values
    s = pd.DataFrame({"p": p, "a": act}); s["bin"] = pd.qcut(s.p, 10, duplicates="drop")
    g = s.groupby("bin", observed=True).agg(pred=("p", "mean"), act=("a", "mean"))
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.plot([0.3, 0.85], [0.3, 0.85], "--", color="#334155", label="perfect")
    ax.plot(g.pred, g.act, "o-", color="#ef4444", label="Elo-gap matrix (raw)")
    ax.set_xlabel("predicted P(Over 2.5)"); ax.set_ylabel("observed frequency")
    ax.set_title("Fig 3. O/U reliability — raw matrix\nover-predicts (motivates calibration)")
    ax.legend()
    fig.tight_layout(); fig.savefig(FIG / "ou_reliability.png"); plt.close(fig)


def fig_sim_state():
    d = json.load(open(MODELS / "sim_fit.json"))
    order = ["lead2", "lead1", "trail1", "trail2"]
    naive = [d["naive_mult_confounded"][k] for k in order]
    ctrl = [d["controlled_mult"][k] for k in order]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    x = np.arange(len(order)); w = 0.38
    ax.bar(x - w / 2, naive, w, label="naive (confounded)", color="#94a3b8")
    ax.bar(x + w / 2, ctrl, w, label="strength-controlled", color=EM)
    ax.axhline(1.0, color="#334155", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(["lead +2", "lead +1", "trail -1", "trail -2"])
    ax.set_ylabel("scoring-rate × vs level")
    ax.set_title("Fig 4. Score-state effect: confound vs causal")
    ax.legend()
    fig.tight_layout(); fig.savefig(FIG / "sim_state.png"); plt.close(fig)


def fig_attdef():       # validated results from §10
    metrics = ["O/U Brier", "total MAE", "score log-loss"]
    elo = [0.2512, 1.477, 2.906]; dc = [0.2522, 1.428, 2.966]; bl = [0.2440, 1.421, 2.887]
    norm = lambda vals: [v / e for v, e in zip(vals, elo)]   # relative to elo-gap=1
    fig, ax = plt.subplots(figsize=(6, 3.2))
    x = np.arange(3); w = 0.26
    ax.bar(x - w, norm(elo), w, label="Elo-gap", color="#94a3b8")
    ax.bar(x, norm(dc), w, label="att/def (DC)", color=SK)
    ax.bar(x + w, norm(bl), w, label="blend 50/50", color=EM)
    ax.axhline(1.0, color="#334155", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(metrics)
    ax.set_ylabel("relative to Elo-gap (lower=better)"); ax.set_ylim(0.95, 1.02)
    ax.set_title("Fig 5. Attack/defence λ blend wins all goal metrics")
    ax.legend()
    fig.tight_layout(); fig.savefig(FIG / "attdef.png"); plt.close(fig)


def fig_xgform():       # §11 results
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar(["goal-form", "xG-form"], [0.0969, 0.1132], color=["#94a3b8", EM])
    ax.set_ylabel("solo R² predicting next margin")
    ax.set_title("Fig 6. xG-form beats goal-form (+17%)")
    for i, v in enumerate([0.0969, 0.1132]):
        ax.text(i, v + 0.001, f"{v:.3f}", ha="center", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "xgform.png"); plt.close(fig)


def fig_architecture():
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    fig, ax = plt.subplots(figsize=(8.2, 6.4)); ax.axis("off")
    ax.set_xlim(0, 10); ax.set_ylim(2.4, 10.4); ax.grid(False)

    def box(x, y, w, h, text, fc, ec="#334155", fs=8.5):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                     fc=fc, ec=ec, lw=1.2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                     mutation_scale=12, color="#475569", lw=1.1))

    BL, GR, AM, PU = "#e0f2fe", "#dcfce7", "#fef3c7", "#ede9fe"
    # row 1: strength inputs
    inps = ["Elo\n(live)", "Seeding /\nsquad prior", "Key\nabsences",
            "Style\nsupremacy", "xG-form\n(in-tourn.)"]
    for i, t in enumerate(inps):
        box(0.2 + i * 1.95, 9.2, 1.7, 0.95, t, BL, fs=7.5)
    box(2.6, 7.9, 3.0, 0.7, "effective Elo", GR)
    box(6.1, 7.9, 3.6, 0.7, "Dixon-Coles att/def", PU)
    for i in range(5):
        arrow(1.05 + i * 1.95, 9.2, 4.1, 8.6)
    # row 2: lambda
    box(3.3, 6.6, 3.4, 0.7, "λ_h , λ_a   (goal-rate blend)", GR, fs=8)
    arrow(4.1, 7.9, 4.6, 7.3); arrow(7.9, 7.9, 6.0, 7.3)
    # ML + market -> headline
    box(0.2, 6.6, 2.7, 0.7, "ML ensemble\n+ market", AM, fs=7.5)
    box(7.0, 6.6, 2.8, 0.7, "headline W/D/L, O/U\n(meta-blend)", AM, fs=7.5)
    arrow(2.9, 6.6, 3.3, 6.6); arrow(6.7, 6.7, 7.0, 6.7)
    # reconcile
    box(3.0, 5.2, 4.0, 0.8, "reconcile_matrix  (IPF)\n→ ONE score matrix M", GR, fs=8)
    arrow(5.0, 6.6, 5.0, 6.0); arrow(8.4, 6.6, 6.5, 6.0); arrow(1.5, 6.6, 3.0, 5.7)
    # markets
    box(0.2, 3.7, 5.0, 0.9, "W/D/L · scorelines · Asian O/U\n(goals & corners) · handicap · BTTS", BL, fs=8)
    box(5.6, 3.7, 4.1, 0.9, "Dixon-Robinson minute MC\n→ scenarios, volatility", PU, fs=8)
    arrow(4.2, 5.2, 2.7, 4.6); arrow(5.8, 5.2, 7.6, 4.6)
    ax.text(5.0, 2.9, "All markets derive from one matrix M → mutually consistent",
            ha="center", fontsize=8.5, style="italic", color="#475569")
    ax.set_title("Fig 0. System architecture", fontsize=11)
    fig.tight_layout(); fig.savefig(FIG / "architecture.png"); plt.close(fig)


# Equations rendered as images (matplotlib mathtext) so they display in ANY
# markdown viewer — GitHub, VS Code preview, PDF — not just MathJax renderers.
EQS = [
    r"P(X{=}x)=\frac{e^{-\lambda}\,\lambda^{x}}{x!}",
    r"P(h,a)=\mathrm{Pois}(h;\lambda_h)\,\mathrm{Pois}(a;\lambda_a)\,\tau_{\rho}(h,a)",
    r"\log\lambda_{\mathrm{home}}=c+\eta+\alpha_h+\beta_a\ ,\quad \log\lambda_{\mathrm{away}}=c+\alpha_a+\beta_h",
    r"E_h=\frac{1}{1+10^{-(R_h+H-R_a)/400}}\ ,\quad R\leftarrow R+K\,(\mathrm{result}-E)",
    r"\lambda=(1-w)\,\exp(a\pm b\,\Delta_{\mathrm{elo}}/100)+w\,\lambda_{\mathrm{dc}}\ ,\quad w=0.5",
    r"p_{\mathrm{wdl}}=\mathrm{norm}(w_{\mathrm{lr}}\,p_{\mathrm{lr}}+w_{\mathrm{xgb}}\,\mathrm{iso}(p_{\mathrm{xgb}}))\ ,\quad w=\mathrm{argmin}\ \mathrm{RPS}",
    r"M=\mathrm{argmin}\ \mathrm{KL}(M\,\|\,M_0)\quad \mathrm{s.t.}\ \ \mathrm{W/D/L,\ Over,\ BTTS\ fixed}",
    r"\tilde{\lambda}\sim\mathrm{Gamma}(k,\theta),\ \ X\,|\,\tilde{\lambda}\sim\mathrm{Pois}(\tilde{\lambda})\ \Rightarrow\ X\sim\mathrm{NegBin}",
    r"\delta=\mathrm{clip}(\mathrm{scale}\cdot\mathrm{signal},\,\pm\mathrm{cap})\cdot\frac{n}{n+k}\ ,\quad \mathrm{eff.Elo}=\mathrm{base}+\sum\delta",
    r"\log\mu=\beta\cdot\mathrm{state}+\log(\mathrm{team\ xG/min})\ ,\quad \mathrm{mult}(\mathrm{state})=e^{\beta}",
]


def make_equations():
    for i, eq in enumerate(EQS, 1):
        fig = plt.figure(figsize=(0.1, 0.1))
        fig.text(0.5, 0.5, rf"$(\,{i}\,)\quad {eq}$", ha="center", va="center", fontsize=15)
        fig.savefig(FIG / f"eq{i}.png", bbox_inches="tight", pad_inches=0.12,
                    dpi=130, facecolor="white"); plt.close(fig)
    print(f"wrote {len(EQS)} equation images")


def main():
    for f in (fig_architecture, fig_corner_determinants, fig_total_dispersion,
              fig_ou_reliability, fig_sim_state, fig_attdef, fig_xgform):
        f(); print("wrote", f.__name__)
    make_equations()
    print("figures ->", FIG)


if __name__ == "__main__":
    main()
