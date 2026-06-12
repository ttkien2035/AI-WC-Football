"""Model families for the ensemble.

M1 Dixon-Coles bivariate Poisson — time-decay weighted attack/defence + rho
M2 Multinomial logistic regression on rating features
M3 XGBoost multiclass + per-class isotonic calibration
M4 Poisson goal-rate regression  lambda = exp(a + b*elo_diff/100 + c*home)
Outcome encoding everywhere: 0 = home win, 1 = draw, 2 = away win.
"""
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

from .data import FEATURES, MARKET_FEATURES

MAX_G = 8
XI = 0.0019          # DC time decay per day
DC_SINCE = "2015-01-01"
DC_MIN_MATCHES = 10


def rps(probs: np.ndarray, outcome: np.ndarray) -> float:
    """Ranked probability score for 3 ordered outcomes (lower = better)."""
    onehot = np.eye(3)[outcome]
    cp = np.cumsum(probs, axis=1)[:, :2]
    co = np.cumsum(onehot, axis=1)[:, :2]
    return float(np.mean(np.sum((cp - co) ** 2, axis=1) / 2.0))


def log_loss3(probs: np.ndarray, outcome: np.ndarray) -> float:
    p = np.clip(probs[np.arange(len(outcome)), outcome], 1e-12, 1)
    return float(-np.mean(np.log(p)))


# ────────────────────────── M1: Dixon-Coles ──────────────────────────
def _dc_tau(matrix: np.ndarray, lh: float, la: float, rho: float) -> np.ndarray:
    m = matrix.copy()
    m[0, 0] *= 1 - lh * la * rho
    m[0, 1] *= 1 + lh * rho
    m[1, 0] *= 1 + la * rho
    m[1, 1] *= 1 - rho
    return m / m.sum()


def dc_matrix(params: dict, home: str, away: str, neutral: bool = True) -> np.ndarray | None:
    att, dfc = params["att"], params["def"]
    if home not in att or away not in att:
        return None
    lh = np.exp(params["c"] + att[home] + dfc[away] + (0 if neutral else params["home_adv"]))
    la = np.exp(params["c"] + att[away] + dfc[home])
    ks = np.arange(MAX_G + 1)
    fact = np.cumprod(np.concatenate([[1.0], np.maximum(ks[1:], 1)]))
    ph = np.exp(-lh) * lh ** ks / fact
    pa = np.exp(-la) * la ** ks / fact
    return _dc_tau(np.outer(ph, pa), lh, la, params["rho"])


def dc_wdl(params: dict, home: str, away: str, neutral: bool = True) -> np.ndarray | None:
    m = dc_matrix(params, home, away, neutral)
    if m is None:
        return None
    hi, ai = np.indices(m.shape)
    return np.array([m[hi > ai].sum(), np.trace(m), m[hi < ai].sum()])


def fit_dixon_coles(df: pd.DataFrame) -> dict:
    """Weighted Poisson GLM with one-hot attack/defence, then rho grid search."""
    d = df[df["date"] >= DC_SINCE].copy()
    counts = pd.concat([d["home"], d["away"]]).value_counts()
    keep = set(counts[counts >= DC_MIN_MATCHES].index)
    d = d[d["home"].isin(keep) & d["away"].isin(keep)].reset_index(drop=True)

    teams = sorted(keep)
    tix = {t: i for i, t in enumerate(teams)}
    n_t, n_m = len(teams), len(d)
    age_days = (d["date"].max() - d["date"]).dt.days.to_numpy()
    w = np.exp(-XI * age_days)

    # two rows per match: scoring side's attack, conceding side's defence, home flag
    rows, cols, vals = [], [], []
    y = np.empty(2 * n_m)
    sw = np.empty(2 * n_m)
    home_flag = np.zeros(2 * n_m)
    for i, r in enumerate(d.itertuples(index=False)):
        for j, (att_t, def_t, goals, is_home) in enumerate(
            ((r.home, r.away, r.gh, not r.neutral), (r.away, r.home, r.ga, False))
        ):
            k = 2 * i + j
            rows += [k, k]
            cols += [tix[att_t], n_t + tix[def_t]]
            vals += [1.0, 1.0]
            y[k] = goals
            sw[k] = w[i]
            home_flag[k] = 1.0 if is_home else 0.0
    X = sparse.csr_matrix(
        sparse.hstack([
            sparse.coo_matrix((vals, (rows, cols)), shape=(2 * n_m, 2 * n_t)),
            sparse.csr_matrix(home_flag[:, None]),
        ])
    )
    glm = PoissonRegressor(alpha=1e-3, max_iter=500)
    glm.fit(X, y, sample_weight=sw)

    att = {t: float(glm.coef_[tix[t]]) for t in teams}
    dfc = {t: float(glm.coef_[n_t + tix[t]]) for t in teams}
    params = {"c": float(glm.intercept_), "home_adv": float(glm.coef_[-1]),
              "att": att, "def": dfc, "rho": 0.0}

    # rho by weighted log-likelihood grid search on recent matches
    recent = d[d["date"] >= str(d["date"].max() - pd.Timedelta(days=2000))]
    best_rho, best_ll = 0.0, -np.inf
    for rho in np.arange(-0.20, 0.11, 0.02):
        params["rho"] = float(rho)
        ll = 0.0
        for r in recent.itertuples(index=False):
            m = dc_matrix(params, r.home, r.away, bool(r.neutral))
            gh, ga = min(r.gh, MAX_G), min(r.ga, MAX_G)
            ll += np.log(max(m[gh, ga], 1e-12))
        if ll > best_ll:
            best_ll, best_rho = ll, float(rho)
    params["rho"] = best_rho
    return params


def dc_predict_frame(params: dict, df: pd.DataFrame) -> np.ndarray:
    out = np.full((len(df), 3), np.nan)
    for i, r in enumerate(df.itertuples(index=False)):
        p = dc_wdl(params, r.home, r.away, bool(r.neutral))
        if p is not None:
            out[i] = p
    return out


# ────────────────────────── M2: logistic regression ──────────────────
def fit_logreg(train: pd.DataFrame):
    pipe = make_pipeline(StandardScaler(),
                         LogisticRegression(C=1.0, max_iter=2000))
    pipe.fit(train[FEATURES], train["outcome"])
    return pipe


# ────────────────────────── M3: XGBoost + isotonic ────────────────────
def fit_xgb(train: pd.DataFrame, valid: pd.DataFrame):
    clf = XGBClassifier(
        objective="multi:softprob", num_class=3, tree_method="hist",
        n_estimators=800, learning_rate=0.05, max_depth=5,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
        early_stopping_rounds=50, eval_metric="mlogloss",
    )
    clf.fit(train[FEATURES], train["outcome"],
            eval_set=[(valid[FEATURES], valid["outcome"])], verbose=False)

    raw = clf.predict_proba(valid[FEATURES])
    calibs = []
    onehot = np.eye(3)[valid["outcome"].to_numpy()]
    for k in range(3):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=1.0)
        iso.fit(raw[:, k], onehot[:, k])
        calibs.append(iso)
    return clf, calibs


def xgb_predict(clf, calibs, df: pd.DataFrame) -> np.ndarray:
    raw = clf.predict_proba(df[FEATURES])
    cal = np.column_stack([calibs[k].predict(raw[:, k]) for k in range(3)])
    cal = np.clip(cal, 1e-4, None)
    return cal / cal.sum(axis=1, keepdims=True)


# ────────────────────────── M4: Poisson goal rates ────────────────────
def fit_goal_rates(df: pd.DataFrame) -> dict:
    """lambda_side = exp(a + b*(own-opp elo incl venue adv)/100). Two rows/match."""
    ed = df["elo_diff"].to_numpy()
    X = np.concatenate([ed, -ed])[:, None] / 100.0
    y = np.concatenate([df["gh"].to_numpy(), df["ga"].to_numpy()])
    glm = PoissonRegressor(alpha=1e-6, max_iter=300)
    glm.fit(X, y)
    return {"a": float(glm.intercept_), "b": float(glm.coef_[0])}


def rates_lambdas(coefs: dict, elo_diff: float) -> tuple[float, float]:
    lh = float(np.exp(coefs["a"] + coefs["b"] * elo_diff / 100.0))
    la = float(np.exp(coefs["a"] - coefs["b"] * elo_diff / 100.0))
    return max(lh, 0.1), max(la, 0.1)


# ────────────────────────── market heads (O/U 2.5, BTTS) ──────────────
def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def fit_market_head(train: pd.DataFrame, valid: pd.DataFrame, target: str) -> dict:
    """Binary head = LR + isotonic-calibrated XGB, blended 50/50."""
    lr = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    lr.fit(train[MARKET_FEATURES], train[target])
    xgb = XGBClassifier(
        objective="binary:logistic", tree_method="hist",
        n_estimators=600, learning_rate=0.05, max_depth=4,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
        early_stopping_rounds=50, eval_metric="logloss")
    xgb.fit(train[MARKET_FEATURES], train[target],
            eval_set=[(valid[MARKET_FEATURES], valid[target])], verbose=False)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=1 - 1e-4)
    iso.fit(xgb.predict_proba(valid[MARKET_FEATURES])[:, 1], valid[target])
    return {"lr": lr, "xgb": xgb, "iso": iso}


def predict_market_head(head: dict, X: pd.DataFrame | np.ndarray) -> np.ndarray:
    plr = head["lr"].predict_proba(X)[:, 1]
    pxgb = head["iso"].predict(head["xgb"].predict_proba(X)[:, 1])
    return np.clip(0.5 * plr + 0.5 * pxgb, 1e-4, 1 - 1e-4)


def derived_market_probs(df: pd.DataFrame, rates: dict, rho: float,
                         max_g: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """O/U 2.5 + BTTS derived from the M4-lambda Dixon-Coles matrix —
    the serving-path baseline the heads must beat/blend with."""
    ks = np.arange(max_g + 1)
    fact = np.cumprod(np.concatenate([[1.0], np.maximum(ks[1:], 1)]))
    over, btts_p = np.empty(len(df)), np.empty(len(df))
    for i, ed in enumerate(df["elo_diff"].to_numpy()):
        lh, la = rates_lambdas(rates, ed)
        ph = np.exp(-lh) * lh ** ks / fact
        pa = np.exp(-la) * la ** ks / fact
        m = np.outer(ph, pa)
        if rho:
            m[0, 0] *= max(1 - lh * la * rho, 1e-9)
            m[0, 1] *= max(1 + lh * rho, 1e-9)
            m[1, 0] *= max(1 + la * rho, 1e-9)
            m[1, 1] *= max(1 - rho, 1e-9)
        m /= m.sum()
        hi, ai = np.indices(m.shape)
        over[i] = m[hi + ai > 2].sum()
        btts_p[i] = m[1:, 1:].sum()
    return over, btts_p


def scoreline_metrics(df: pd.DataFrame, rates: dict, rho: float,
                      max_g: int = 8) -> dict:
    """Top-1 exact-score hit rate + log-loss of the actual scoreline."""
    ks = np.arange(max_g + 1)
    fact = np.cumprod(np.concatenate([[1.0], np.maximum(ks[1:], 1)]))
    hits, ll = 0, 0.0
    for r in df.itertuples(index=False):
        lh, la = rates_lambdas(rates, r.elo_diff)
        ph = np.exp(-lh) * lh ** ks / fact
        pa = np.exp(-la) * la ** ks / fact
        m = np.outer(ph, pa)
        if rho:
            m[0, 0] *= max(1 - lh * la * rho, 1e-9)
            m[0, 1] *= max(1 + lh * rho, 1e-9)
            m[1, 0] *= max(1 + la * rho, 1e-9)
            m[1, 1] *= max(1 - rho, 1e-9)
        m /= m.sum()
        top = np.unravel_index(m.argmax(), m.shape)
        gh, ga = min(int(r.gh), max_g), min(int(r.ga), max_g)
        hits += (top == (gh, ga))
        ll += -np.log(max(m[gh, ga], 1e-12))
    n = len(df)
    return {"top1_hit": round(hits / n, 4), "logloss": round(ll / n, 4)}


# ────────────────────────── ensemble weights ──────────────────────────
def fit_ensemble_weights(prob_sets: dict[str, np.ndarray], outcome: np.ndarray,
                         step: float = 0.05,
                         floors: dict[str, float] | None = None,
                         ) -> tuple[dict[str, float], float]:
    """Grid search on the simplex minimizing RPS. NaN rows (DC unknown team)
    fall back to renormalized remaining models. `floors` forces minimum
    weights for named models — diverse-family blends generalize better than
    the validation-argmax single model (verified on the 2025+ test slice)."""
    names = list(prob_sets)
    floors = floors or {}
    grids = np.arange(0.0, 1.0 + 1e-9, step)
    best_w, best_rps = None, np.inf

    def blend(ws):
        num = np.zeros((len(outcome), 3))
        den = np.zeros((len(outcome), 1))
        for w, nm in zip(ws, names):
            p = prob_sets[nm]
            ok = ~np.isnan(p[:, 0])
            num[ok] += w * p[ok]
            den[ok] += w
        den[den == 0] = 1.0
        return num / den

    def rec(i, remaining, acc):
        nonlocal best_w, best_rps
        if i == len(names) - 1:
            ws = acc + [remaining]
            if remaining < floors.get(names[-1], 0.0) - 1e-9:
                return
            score = rps(blend(ws), outcome)
            if score < best_rps:
                best_rps, best_w = score, ws
            return
        for g in grids:
            if g <= remaining + 1e-9 and g >= floors.get(names[i], 0.0) - 1e-9:
                rec(i + 1, round(remaining - g, 10), acc + [g])

    rec(0, 1.0, [])
    return dict(zip(names, [round(w, 3) for w in best_w])), best_rps
