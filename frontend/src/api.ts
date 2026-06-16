export type TeamRow = {
  id: number; name: string; tla: string; crest: string | null; group: string;
  position: number; played: number; won: number; draw: number; lost: number;
  gf: number; ga: number; gd: number; points: number; form: string | null;
  elo: number; fifa_rank: number | null; pot: number | null;
  sim?: SimTeam | null;
};

export type SimTeam = {
  win_group: number; r32: number; r16: number; qf: number; sf: number;
  final: number; champion: number;
};

export type Incident = {
  minute: number | null; type: "goal" | "yellow" | "red";
  own_goal?: boolean; penalty?: boolean;
  player: string | null; side: "home" | "away" | "?";
};

export type LineupSide = {
  formation: string | null;
  players: { name: string; pos: string | null; shirt: number | null }[];
};

export type Match = {
  id: number; utcDate: string; status: string; stage: string;
  group: string | null; matchday: number | null;
  home: { id: number | null; name: string | null; tla: string | null; crest: string | null };
  away: { id: number | null; name: string | null; tla: string | null; crest: string | null };
  score: { home: number | null; away: number | null; winner: string | null };
  minute_estimate?: number | null;
  minute_source?: string;
  ht_score?: { home: number; away: number };
  corners?: { home: number | null; away: number | null };
  stats?: Record<string, { home: number | null; away: number | null }>;
  red_cards?: { home: number; away: number };
  incidents?: Incident[];
  lineups?: { home?: LineupSide | null; away?: LineupSide | null };
};

export type TimelinePoint = {
  ts: string; minute: number | null;
  score: { home: number; away: number } | null;
  probs: { home: number; draw: number; away: number };
};

export type KeyPlayer = { name: string; pos: string; w: number; status: "in_xi" | "missing" | "unknown" };

export type Analysis = {
  home: string; away: string; lineups_announced: boolean; stage: string | null;
  teams: Record<string, {
    profile: { formation?: string; style?: string[]; manager?: string; value_tier?: number };
    manager_note?: string | null;
    lineup: LineupSide | null;
    formation_live: string | null;
    key_players: KeyPlayer[];
    absence_elo_penalty: number;
    observed_style: {
      n: number; confidence: number; possession: number; shots: number;
      crosses: number; fouls: number; xg_for: number; xg_against: number;
    } | null;
    effective_style: string[] | null;
    squad: { name: string; position: string | null }[];
    elo: number; fifa_rank: number | null;
  }>;
};

export type Prediction = {
  home: string; away: string; in_play: boolean; minute: number | null;
  fixture_status: string | null;
  score: { home: number; away: number } | null;
  lambdas: Record<string, number>;
  probs: { home: number; draw: number; away: number };
  components: {
    poisson: Record<string, number>;
    elo: Record<string, number>;
    market: Record<string, number> | null;
    ml: Record<string, number> | null;
    form: { home: number | null; away: number | null; delta: number };
    weights: Record<string, number>;
    style?: { total_factor: number; reason: string | null };
    context?: {
      factor: number;
      stakes?: { home: string; away: string } | null;
      seeding?: { team: string; gap: number } | null;
      lockdown_underdog?: string | null;
      notes: { key: string; params: Record<string, string | number> }[];
    };
    venue?: { factor: number; venue: { stadium: string; city: string; alt: number; roof: boolean } | null };
  };
  over25: number; btts: number;
  scorelines: { home: number; away: number; p: number }[];
  elo: { home: number; away: number; expectancy: number };
  stage?: string | null;
  is_knockout?: boolean;
  market_lines?: {
    goals: LineOU; corners: LineOU;
    handicap?: {
      line: number; home: number; push: number; away: number;
      pick: "home" | "away"; pick_tla: string; fav_tla: string;
      exp_margin: number; source: string; confidence: string;
      market?: Record<string, number | null> | null;
    };
  };
  halves?: {
    h1?: { probs?: Record<string, number>; top_scores?: ScoreP[]; lambdas?: number[]; note?: string; final?: unknown };
    h2?: { probs?: Record<string, number>; top_scores?: ScoreP[]; lambdas?: number[]; note?: string };
    htft?: Record<string, number>;
  };
  corners?: {
    expected: { home: number; away: number; total: number; h1: number; h2: number };
    over: Record<string, number>;
    in_play?: { so_far: Record<string, number>; projected_total: number };
  };
  knockout?: {
    regulation: Record<string, number>;
    p_extra_time: number; p_penalties: number;
    pens_win: { home: number; away: number };
    advance: { home: number; away: number };
    win_via: Record<string, Record<string, number>>;
  };
  simulation?: {
    probs: { home: number; draw: number; away: number };
    scorelines: ScoreP[];
    exp_goals: { home: number; away: number };
    scenarios: {
      ht_flip: number;
      late_goal_80plus: number; home_blew_lead: number; home_comeback: number;
      clean_sheet_home: number; clean_sheet_away: number;
    };
    from: { minute: number; score: { home: number; away: number } };
    runs: number;
  };
  volatility?: { ht_flip: number; level: "low" | "medium" | "high" };
};

export type ScoreP = { home: number; away: number; p: number };

export type LineOU = {
  line: number; over: number; under: number; push: number;
  market: { over: number | null; under: number | null } | null;
  source: "market" | "default";
  pick?: "over" | "under";
  confidence?: "toss_up" | "lean" | "clear";
};

export type OddsRow = {
  match_id: number; utcDate: string; stage: string; group: string | null;
  home: Match["home"]; away: Match["away"];
  fair: {
    h2h: Record<string, number | null>; probs: Record<string, number>;
    over25: number | null; under25: number | null; btts_yes: number | null;
    corners_over_95: number | null; expected_corners: number;
  };
  market: {
    h2h?: Record<string, number> | null;
    totals?: { point: number; over?: number; under?: number } | null;
    spreads?: { point: number; home?: number; away?: number } | null;
    btts?: { yes: number; no: number } | null;
    corners_totals?: { point: number; over: number | null; under: number | null }[] | null;
  } | null;
  value?: Record<string, number>;
};

export type BracketEntry = {
  home_top: { tla: string; p: number }[];
  away_top: { tla: string; p: number }[];
  winner_top: { tla: string; p: number }[];
};

export type Simulation = {
  runs: number;
  computed_at: string;
  teams: Record<string, SimTeam>;
  bracket: Record<string, BracketEntry>;
};

const j = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
};

// ── Admin (X-Admin-Token gated endpoints) ─────────────────────
export const adminToken = {
  get: () => localStorage.getItem("admin_token"),
  set: (t: string) => localStorage.setItem("admin_token", t),
  clear: () => localStorage.removeItem("admin_token"),
};

export const jAdmin = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(url, {
    ...init,
    headers: { ...(init?.headers ?? {}), "X-Admin-Token": adminToken.get() ?? "" },
  });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
};

export const api = {
  teams: () => j<Record<string, TeamRow>>("/api/teams"),
  groups: () =>
    j<{ groups: Record<string, TeamRow[]>; sim_meta: { runs: number; computed_at: string } | null }>(
      "/api/groups"),
  matches: (q = "") => j<{ matches: Match[] }>(`/api/matches${q}`),
  live: () => j<{ live: Match[]; today: Match[] }>("/api/live"),
  predict: (h: string, a: string, params = "") =>
    j<Prediction>(`/api/match/${h}/${a}/predict${params}`),
  simulate: () => j<Simulation>("/api/simulate"),
  bracket: () =>
    j<{ routing: Record<string, Record<string, [string, string]>>; sim: Record<string, BracketEntry>; real: Record<string, Match[]>; schedule: Record<string, { date: string; city: string }>; meta: { runs: number; computed_at: string } }>(
      "/api/bracket"),
  sources: () => j<Record<string, { ok: boolean; source?: string; [k: string]: unknown }>>("/api/sources/status"),
  odds: (limit = 24) =>
    j<{ matches: OddsRow[]; source: string; quota: { remaining: string } | null; ml: boolean }>(
      `/api/odds?limit=${limit}`),
  timeline: (id: number) => j<{ points: TimelinePoint[] }>(`/api/live/${id}/timeline`),
  results: (n = 10) => j<{ results: ResultMatch[] }>(`/api/results?n=${n}`),
  evalTournament: () => j<TournamentEval>("/api/evaluate/tournament"),
  analysis: (h: string, a: string) => j<Analysis>(`/api/match/${h}/${a}/analysis`),
  evalH2h: (h: string, a: string, n = 10) => j<EvalResult>(`/api/evaluate/h2h/${h}/${a}?n=${n}`),
  evalTeam: (tla: string, n = 12) => j<EvalResult>(`/api/evaluate/team/${tla}?n=${n}`),
  mlStatus: () => j<MlStatus>("/api/ml/status"),
  pipelineStatus: () => jAdmin<PipelineStatus>("/api/pipeline/status"),
  pipelineReview: (limit = 30) => jAdmin<PipelineReview>(`/api/pipeline/review?limit=${limit}`),
  mlRetrain: () => jAdmin<{ ok: boolean }>("/api/ml/retrain", { method: "POST" }),
  pipelineAnalytics: (days = 14) => jAdmin<Analytics>(`/api/pipeline/analytics?days=${days}`),
};

export type Analytics = {
  kpis: {
    visitors: number; events: number; events_per_visitor: number;
    active_today: number; active_yesterday: number;
    returning: number; returning_pct: number;
  };
  daily: { date: string; visitors: number; events: number }[];
  hourly: { hour: number; n: number }[];
  features: { feature: string; visitors: number }[];
  tabs: { tab: string; n: number }[];
  matchups: { pair: string; n: number }[];
  langs: { lang: string; n: number }[];
  totals: { visitors: number; events: number };
};

export type PipelineStatus = {
  collection: {
    matches_total: number; finished: number; live_now: number;
    match_log: number; prematch_snapshots: number; timeline_series: number;
    teams_with_corner_stats: number;
  };
  scheduler: { last_tick: string | null; live_mode: boolean };
  ml: {
    available: boolean; online_updates_applied: number;
    last_retrain: string | null; retraining_now: boolean;
    next_retrain_utc: string; weights: Record<string, number> | null;
    test_rps: number | null;
  };
  elo_movers: { tla: string; delta: number; elo: number }[];
  factor_scorecard: Record<string, {
    n: number; metric: string; with?: number; without?: number;
    delta?: number; verdict: string;
  }>;
  sim_timing: Record<string, {
    n: number; pred_mean?: number; actual_rate?: number; brier?: number;
  }>;
  corners_scorecard: {
    n: number; brier: number | null; hit_rate: number | null;
    pred_mean_total: number | null; actual_mean_total: number | null;
    club_base: number; observed_mean: number | null; adaptive_base: number;
  };
  meta_weights: {
    enabled: boolean; active?: boolean; n: number; reason?: string;
    hand: Record<string, number>; served?: Record<string, number>;
    fitted?: Record<string, number>; shrink_lambda?: number;
    rps_hand?: number; rps_fitted?: number;
  };
  sources: Record<string, { ok: boolean }>;
};

export type ReviewRow = {
  match_id: number; date: string; stage: string;
  home: Match["home"]; away: Match["away"];
  score: { home: number; away: number };
  ht_score?: { home: number; away: number } | null;
  probs: Record<string, number>; probs_source: string;
  predicted: string; actual: string; correct: boolean;
  p_actual: number; tag: string;
  factors: {
    red_cards?: { home: number; away: number } | null;
    corners?: { home: number | null; away: number | null } | null;
    ht_swing: boolean;
    absence?: unknown; lineup_aware?: boolean;
  };
  compare?: CompareBlock;
  notes?: { key: string; params: Record<string, string | number> }[];
  improve?: string | null;
  elo_shift: { home: number; away: number } | null;
};
export type PipelineReview = {
  matches: ReviewRow[];
  summary: { n: number; correct: number; accuracy: number; rps: number; logloss: number } | null;
};

export type ResultMatch = {
  id: number; date: string; stage: string; group: string | null;
  home: Match["home"]; away: Match["away"];
  score: { home: number; away: number } | null;
  ht_score?: { home: number; away: number } | null;
  corners?: { home: number | null; away: number | null } | null;
  stats?: Record<string, { home: number | null; away: number | null }> | null;
  incidents: Incident[];
};

export type CompareBlock = {
  winner: { pred: string; actual: string; hit: boolean };
  score: { pred: string | null; actual: string; hit: boolean };
  total_goals: { pred_xg: number | null; actual: number };
  over25: { pred_p: number | null; actual: boolean };
  // total-goals O/U graded at the market's ASIAN line (e.g. 2.75), not fixed 2.5
  goals: {
    line?: number; p_over?: number; pick?: "over" | "under";
    actual_total?: number | null; actual?: "over" | "under" | "push";
    hit?: boolean; line_source?: string; pred_p?: number | null;
  };
  btts: { pred_p: number | null; actual: boolean };
  corners: {
    // O/U verdict shape (new snapshots) — falls back to expectation-only
    line?: number; p_over?: number; pick?: "over" | "under";
    expected_total?: number | null; actual_total?: number | null;
    actual?: "over" | "under" | "push"; hit?: boolean; line_source?: string;
    pred?: number | null;
    detail: { home: number | null; away: number | null } | null;
  };
};

export type TournamentEval = {
  matches: {
    match_id: number; date: string; stage: string;
    home: Match["home"]; away: Match["away"];
    score: { home: number; away: number };
    ht_score?: { home: number; away: number } | null;
    probs: Record<string, number>;
    predicted: string; actual: string; correct: boolean;
    p_actual: number; tag: string; compare: CompareBlock;
  }[];
  summary: { n: number; correct: number; accuracy: number; rps: number } | null;
};

export type EvalMatch = {
  date: string; tournament: string; home: string; away: string; score: string;
  probs: Record<string, number>; predicted: string; actual: string; correct: boolean;
};
export type EvalResult = {
  matches: EvalMatch[];
  summary: { n: number; accuracy: number; rps: number } | null;
  error?: string;
};
export type MlStatus = {
  available: boolean;
  report: {
    test_metrics: Record<string, { rps: number; logloss: number; acc: number; n: number }>;
    weights: Record<string, number>;
    scoreline?: {
      poisson: { top1_hit: number; logloss: number };
      dixon_coles: { top1_hit: number; logloss: number };
    };
    markets?: Record<string, Record<string, { brier: number; acc: number } | number>>;
  } | null;
  last_retrain: string | null;
  retraining_now: boolean;
  online_updates_applied: number;
};

export const pct = (p: number | undefined | null, digits = 1) =>
  p == null ? "–" : `${(p * 100).toFixed(digits)}%`;
