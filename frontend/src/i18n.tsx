import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "vi" | "en";

const DICT: Record<string, { vi: string; en: string }> = {
  // App shell
  "app.title": { vi: "World Cup 2026", en: "World Cup 2026" },
  "app.subtitle": { vi: "AI Dự đoán", en: "AI Predictor" },
  "tab.groups": { vi: "Vòng bảng", en: "Groups" },
  "tab.bracket": { vi: "Nhánh đấu", en: "Bracket" },
  "tab.match": { vi: "Dự đoán trận", en: "Match Sim" },
  "tab.title": { vi: "Cửa vô địch", en: "Title Odds" },
  "tab.odds": { vi: "Tỉ lệ kèo", en: "Odds" },
  "tab.accuracy": { vi: "Độ chính xác", en: "Accuracy" },
  "app.refresh": { vi: "Ép cập nhật dữ liệu + mô phỏng lại", en: "Force refresh + re-simulate" },
  "app.footer": {
    vi: "Poisson + Elo + ML ensemble + kèo thị trường · Monte Carlo · dữ liệu: football-data.org, LiveScore, eloratings.net, The Odds API · chỉ mang tính tham khảo, không phải khuyến nghị cá cược",
    en: "Poisson + Elo + ML ensemble + market odds · Monte Carlo · data: football-data.org, LiveScore, eloratings.net, The Odds API · for reference only, not betting advice",
  },
  "app.today": { vi: "Hôm nay", en: "Today" },

  // Groups
  "groups.note": { vi: "Xác suất đi tiếp từ {runs} lượt mô phỏng Monte Carlo · {time}", en: "Qualification odds from {runs} Monte Carlo runs · {time}" },
  "groups.group": { vi: "BẢNG", en: "GROUP" },
  "groups.team": { vi: "Đội", en: "Team" },
  "groups.adv": { vi: "Đi tiếp", en: "Adv %" },
  "groups.failed": { vi: "Không tải được vòng bảng: ", en: "Failed to load groups: " },

  // Bracket
  "bracket.note": {
    vi: "Xác suất từng cặp từ {runs} lượt mô phỏng. Chip = đội nhiều khả năng thắng cặp đó. Đội thật sẽ thay thế dự phóng khi giải tiến triển.",
    en: "Per-slot probabilities from {runs} simulations. Chips show the most likely winner of each tie. Real teams replace projections as the tournament progresses.",
  },
  "bracket.r32": { vi: "Vòng 1/16", en: "Round of 32" },
  "bracket.r16": { vi: "Vòng 1/8", en: "Round of 16" },
  "bracket.qf": { vi: "Tứ kết", en: "Quarter-finals" },
  "bracket.sf": { vi: "Bán kết", en: "Semi-finals" },
  "bracket.final": { vi: "Chung kết", en: "Final" },

  // Match Sim
  "match.setup": { vi: "Thiết lập trận đấu", en: "Match setup" },
  "match.live_now": { vi: "ĐANG ĐÁ", en: "LIVE NOW" },
  "match.upcoming": { vi: "Trận sắp tới — bấm để dự đoán", en: "Upcoming — tap to predict" },
  "match.home": { vi: "Đội nhà", en: "Home" },
  "match.away": { vi: "Đội khách", en: "Away" },
  "match.inplay": { vi: "In-play (nhập phút & tỉ số)", en: "In-play override (minute & score)" },
  "match.minute": { vi: "Phút", en: "Minute" },
  "match.goals": { vi: "bàn", en: "goals" },
  "match.predict": { vi: "Dự đoán", en: "Predict" },
  "match.simulating": { vi: "Đang tính…", en: "Simulating…" },
  "match.pick_two": { vi: "Chọn hai đội khác nhau.", en: "Pick two different teams." },
  "match.empty": { vi: "Chọn hai đội rồi bấm", en: "Pick two teams and hit" },
  "match.win": { vi: "thắng", en: "win" },
  "match.draw": { vi: "Hòa", en: "Draw" },
  "match.over25": { vi: "Tài 2.5", en: "Over 2.5" },
  "match.btts": { vi: "2 đội ghi bàn", en: "BTTS" },
  "match.scorelines": { vi: "Tỉ số khả năng nhất", en: "Most likely scorelines" },
  "match.components": { vi: "Thành phần model (W/D/L)", en: "Model components (W/D/L)" },
  "match.source": { vi: "Nguồn", en: "Source" },
  "match.weight": { vi: "Trọng số", en: "Weight" },
  "match.ml_row": { vi: "ML ensemble (XGB+LR)", en: "ML ensemble (XGB+LR)" },
  "match.poisson_row": { vi: "Poisson (Elo+stats)", en: "Poisson (Elo+stats)" },
  "match.elo_row": { vi: "Kỳ vọng Elo", en: "Elo expectancy" },
  "match.market_row": { vi: "Kèo thị trường (de-vig)", en: "Market odds (de-vig)" },
  "match.no_market": {
    vi: "Chưa có kèo thị trường (thiếu ODDS_API_KEY hoặc trận chưa có giá) — chỉ dùng model.",
    en: "Market odds unavailable (no ODDS_API_KEY or no quote for this fixture) — model blend only.",
  },
  "match.halves": { vi: "Theo hiệp đấu", en: "By half" },
  "match.h1": { vi: "Hiệp 1", en: "1st half" },
  "match.h2": { vi: "Hiệp 2", en: "2nd half" },
  "match.htft": { vi: "HT/FT (hiệp 1 / cả trận) — top 5", en: "HT/FT (half-time / full-time) — top 5" },
  "match.corners": { vi: "Phạt góc (dự đoán)", en: "Corners (predicted)" },
  "match.corners_total": { vi: "Tổng", en: "Total" },
  "match.corners_sofar": { vi: "Đã có {h}–{a} góc · dự kiến cả trận ~{t}", en: "{h}–{a} corners so far · projected total ~{t}" },
  "match.ko": { vi: "Hiệp phụ & luân lưu", en: "Extra time & penalties" },
  "match.ko_if": { vi: "(nếu là trận knockout)", en: "(if knockout)" },
  "match.ko_90": { vi: "Phân định 90'", en: "Decided in 90'" },
  "match.ko_et": { vi: "Vào hiệp phụ", en: "Extra time" },
  "match.ko_pens": { vi: "Đến luân lưu", en: "Penalties" },
  "match.ko_pen_win": { vi: "Pen: {team}", en: "Pens: {team}" },
  "match.advance": { vi: "{team} đi tiếp", en: "{team} advances" },
  "match.via": { vi: "{team} thắng qua: 90' {a} · hiệp phụ {b} · pen {c}", en: "{team} wins via: 90' {a} · ET {b} · pens {c}" },
  "match.h2h": { vi: "Đối đầu gần đây — model đoán đúng?", en: "Recent H2H — did the model get it right?" },
  "match.h2h_acc": { vi: "Model đúng {c}/{n} trận gần nhất (RPS {rps})", en: "Model correct in {c}/{n} recent meetings (RPS {rps})" },
  "match.h2h_none": { vi: "Chưa có dữ liệu đối đầu từ 2018.", en: "No H2H data since 2018." },
  "match.pred": { vi: "đoán", en: "pred" },

  // Title odds
  "title.champion": { vi: "Vô địch", en: "Champion" },
  "title.final": { vi: "Vào chung kết", en: "Reach Final" },
  "title.sf": { vi: "Bán kết", en: "Semi-final" },
  "title.qf": { vi: "Tứ kết", en: "Quarter-final" },
  "title.r16": { vi: "Vòng 1/8", en: "Round of 16" },
  "title.r32": { vi: "Vòng 1/16", en: "Round of 32" },
  "title.heading": { vi: "Xác suất {metric} — top 20", en: "{metric} probability — top 20" },
  "title.note": { vi: "{runs} lượt mô phỏng Monte Carlo · cập nhật {time}", en: "{runs} Monte Carlo tournament simulations · updated {time}" },

  // Odds
  "odds.no_key": {
    vi: "Chưa có ODDS_API_KEY trong .env — đang hiển thị fair odds từ model (1/xác suất). Đăng ký key miễn phí tại the-odds-api.com để xem kèo thị trường thật (1X2, chấp, tài xỉu, phạt góc).",
    en: "No ODDS_API_KEY in .env — showing model fair odds (1/probability). Get a free key at the-odds-api.com for real market odds (1X2, handicap, totals, corners).",
  },
  "odds.quota": { vi: "The Odds API còn lại: {n} credits", en: "The Odds API quota remaining: {n}" },
  "odds.market": { vi: "Thị trường", en: "Market" },
  "odds.model": { vi: "Model (fair)", en: "Model (fair)" },
  "odds.bet": { vi: "Kèo", en: "Market" },
  "odds.ou": { vi: "Tài/Xỉu 2.5", en: "O/U 2.5" },
  "odds.ah": { vi: "Chấp (AH)", en: "Handicap" },
  "odds.corners": { vi: "Phạt góc", en: "Corners" },
  "odds.value": { vi: "Value: {v} (model đánh giá xác suất cao hơn thị trường)", en: "Value: {v} (model rates probability above market)" },
  "odds.footer": { vi: "Fair odds = 1 / xác suất model (ML ensemble {ml}). Tham khảo thống kê — không phải khuyến nghị cá cược.", en: "Fair odds = 1 / model probability (ML ensemble {ml}). Statistical reference — not betting advice." },
  "odds.legend_title": { vi: "📖 Cách đọc bảng kèo", en: "📖 How to read this board" },
  "odds.legend": {
    vi: "• 1 / X / 2 = đội NHÀ thắng / HÒA / đội KHÁCH thắng. Số là tỉ lệ ăn kiểu decimal: cược 100k ở kèo 1.42 → nhận 142k nếu trúng. Số càng THẤP = khả năng càng cao (kèo trên, in đậm xanh).\n• Tài/Xỉu 2.5: Tài (O) = tổng bàn ≥3, Xỉu (U) = ≤2.\n• Chấp (AH): chấp bàn kiểu châu Á — \"MEX -1.5\" nghĩa là Mexico chấp 1.5 bàn (phải thắng cách biệt 2 bàn mới ăn kèo).\n• Thị trường = giá trung bình các nhà cái (đã gồm lãi nhà cái). Model (fair) = giá \"công bằng\" tính từ xác suất AI (kèm % xác suất), không có lãi.\n• ⚡ Value = model tin xác suất CAO hơn giá thị trường ngụ ý — chênh càng lớn kèo càng \"hời\" theo model.",
    en: "• 1 / X / 2 = HOME win / DRAW / AWAY win. Decimal odds: stake 100 at 1.42 returns 142 if it wins. LOWER = more likely (the favourite, bold green).\n• O/U 2.5: Over = 3+ total goals, Under = ≤2.\n• AH: Asian handicap — \"MEX -1.5\" means Mexico gives 1.5 goals (must win by 2+).\n• Market = average bookmaker price (includes their margin). Model (fair) = the AI's no-margin price, shown with its probability %.\n• ⚡ Value = the model rates a probability HIGHER than the market price implies.",
  },
  "odds.fav": { vi: "kèo trên", en: "favourite" },

  // Accuracy
  "acc.heading": { vi: "Độ chính xác của model", en: "Model accuracy" },
  "acc.backtest": { vi: "Backtest trên tập test 2025–26 (n={n} trận chưa từng thấy khi train)", en: "Backtest on held-out 2025–26 test set (n={n} unseen matches)" },
  "acc.model": { vi: "Model", en: "Model" },
  "acc.rps": { vi: "RPS ↓", en: "RPS ↓" },
  "acc.logloss": { vi: "Log-loss ↓", en: "Log-loss ↓" },
  "acc.accuracy": { vi: "Chính xác", en: "Accuracy" },
  "acc.check_team": { vi: "Kiểm chứng theo đội", en: "Check by team" },
  "acc.check_h2h": { vi: "Kiểm chứng cặp đấu (H2H)", en: "Check a matchup (H2H)" },
  "acc.load": { vi: "Xem", en: "Check" },
  "acc.result": { vi: "Model đúng {c}/{n} ({pct}) · RPS {rps}", en: "Model correct {c}/{n} ({pct}) · RPS {rps}" },
  "acc.no_data": { vi: "Không có dữ liệu (từ 2018).", en: "No data (since 2018)." },
  "acc.note": {
    vi: "Mỗi trận được dự đoán bằng đúng thông tin có TRƯỚC trận (as-of features) — không rò rỉ dữ liệu tương lai. Model được retrain tự động hàng đêm và ratings update online sau mỗi trận World Cup.",
    en: "Each match is predicted using only information available BEFORE kickoff (as-of features) — no future leakage. Models retrain automatically nightly; ratings update online after every WC match.",
  },
  "acc.last_retrain": { vi: "Retrain gần nhất: {d} · online updates đã áp dụng: {n} trận", en: "Last retrain: {d} · online updates applied: {n} matches" },
  "acc.never": { vi: "chưa (artifacts từ lần train đầu)", en: "not yet (initial training artifacts)" },

  // Live tab
  "tab.live": { vi: "Trực tiếp", en: "Live" },
  "live.none": { vi: "Không có trận nào đang diễn ra.", en: "No match in progress." },
  "live.upcoming": { vi: "Trận sắp diễn ra", en: "Upcoming matches" },
  "live.kickoff_in": { vi: "Bóng lăn sau", en: "Kick-off in" },
  "live.winprob": { vi: "Xác suất thắng (cập nhật trực tiếp)", en: "Win probability (live)" },
  "live.chart": { vi: "Diễn biến xác suất theo phút", en: "Win probability timeline" },
  "live.chart_empty": { vi: "Biểu đồ sẽ tích điểm sau vài phút trận đấu…", en: "Chart accumulates points as the match progresses…" },
  "live.events": { vi: "Diễn biến trận đấu", en: "Match events" },
  "live.no_events": { vi: "Chưa có sự kiện (hoặc nguồn LiveScore chưa trả).", en: "No events yet (or LiveScore source pending)." },
  "live.corners": { vi: "Phạt góc", en: "Corners" },
  "live.lineups": { vi: "Đội hình xuất phát", en: "Starting lineups" },
  "live.lineups_tba": { vi: "Đội hình chưa công bố (thường ~1h trước giờ đá).", en: "Lineups not announced yet (usually ~1h before kick-off)." },
  "live.own_goal": { vi: "phản lưới", en: "own goal" },
  "live.pen": { vi: "pen", en: "pen" },
  "live.updated": { vi: "Tự cập nhật mỗi 20 giây", en: "Auto-refreshes every 20s" },

  // Analysis
  "ana.heading": { vi: "Phân tích chiến thuật", en: "Tactical analysis" },
  "ana.formation": { vi: "Sơ đồ", en: "Formation" },
  "ana.live_xi": { vi: "(XI thật)", en: "(announced XI)" },
  "ana.manager": { vi: "HLV", en: "Manager" },
  "ana.style": { vi: "Lối chơi", en: "Style" },
  "ana.value": { vi: "Giá trị đội hình", en: "Squad value" },
  "ana.key_players": { vi: "Trụ cột", en: "Key players" },
  "ana.in_xi": { vi: "đá chính", en: "starting" },
  "ana.missing": { vi: "vắng mặt", en: "missing" },
  "ana.unknown": { vi: "chưa rõ", en: "TBC" },
  "ana.penalty_note": { vi: "Vắng trụ cột → model đã trừ {n} Elo (nghiên cứu: vắng ngôi sao dịch odds 10–25%).", en: "Key absence → model applied {n} Elo penalty (research: star absences shift odds 10–25%)." },
  "ana.style_note": { vi: "Lối chơi/chiến thuật chỉ dùng cho phân tích — không chỉnh xác suất (không có dữ liệu calibrate cho ĐTQG). Thẻ đỏ & vắng trụ cột ĐÃ được đưa vào dự đoán.", en: "Style/tactics are analysis-only — not probability nudges (no calibratable data for national teams). Red cards & key absences ARE in the prediction." },
  // style tags
  "style.possession": { vi: "kiểm soát bóng", en: "possession" },
  "style.high_press": { vi: "pressing tầm cao", en: "high press" },
  "style.counter": { vi: "phản công", en: "counter-attack" },
  "style.direct": { vi: "bóng dài trực diện", en: "direct play" },
  "style.low_block": { vi: "phòng ngự lùi sâu", en: "low block" },
  "style.wing_play": { vi: "tấn công biên", en: "wing play" },
  "style.set_pieces": { vi: "bóng chết", en: "set pieces" },
  "style.physical": { vi: "thể lực/tranh chấp", en: "physical" },
  "style.technical": { vi: "kỹ thuật", en: "technical" },
  "style.transition": { vi: "chuyển trạng thái nhanh", en: "fast transitions" },

  // Pipeline (admin)
  "tab.pipeline": { vi: "Pipeline", en: "Pipeline" },
  "pl.heading": { vi: "Giám sát AI/ML Pipeline", en: "AI/ML Pipeline Monitor" },
  "pl.admin_only": { vi: "Khu vực admin", en: "Admin area" },
  "pl.collection": { vi: "Thu thập dữ liệu", en: "Data collection" },
  "pl.matches": { vi: "Trận (lịch)", en: "Fixtures" },
  "pl.finished": { vi: "Đã kết thúc", en: "Finished" },
  "pl.live_now": { vi: "Đang live", en: "Live now" },
  "pl.match_log": { vi: "Match log", en: "Match log" },
  "pl.prematch": { vi: "Snapshot pre-match", en: "Pre-match snapshots" },
  "pl.timeline": { vi: "Timeline series", en: "Timeline series" },
  "pl.corner_teams": { vi: "Đội có data góc", en: "Teams w/ corner data" },
  "pl.scheduler": { vi: "Scheduler tick gần nhất: {t} · chế độ live: {live}", en: "Last scheduler tick: {t} · live mode: {live}" },
  "pl.ml": { vi: "Trạng thái Model", en: "Model status" },
  "pl.online_updates": { vi: "Online updates đã áp", en: "Online updates applied" },
  "pl.last_retrain": { vi: "Retrain gần nhất", en: "Last retrain" },
  "pl.next_retrain": { vi: "Retrain kế tiếp", en: "Next retrain" },
  "pl.retrain_now": { vi: "Retrain ngay", en: "Retrain now" },
  "pl.retraining": { vi: "Đang retrain…", en: "Retraining…" },
  "pl.retrain_confirm": { vi: "Tải dataset mới + train lại 4 models (vài phút)?", en: "Download fresh data + retrain all 4 models (takes minutes)?" },
  "pl.movers": { vi: "Elo dịch chuyển trong giải (online update)", en: "In-tournament Elo movers (online updates)" },
  "pl.review": { vi: "Đối chiếu dự đoán vs kết quả", en: "Predictions vs results" },
  "pl.review_sum": { vi: "Đúng {c}/{n} ({pct}) · RPS {rps} · log-loss {ll}", en: "Correct {c}/{n} ({pct}) · RPS {rps} · log-loss {ll}" },
  "pl.no_finished": { vi: "Chưa có trận nào kết thúc — bảng này sẽ tự có dữ liệu sau trận đầu tiên.", en: "No finished matches yet — this table fills in after the first final whistle." },
  "pl.snapshot": { vi: "snapshot trước trận", en: "pre-match snapshot" },
  "pl.asof": { vi: "tính lại as-of (không rò rỉ)", en: "as-of recompute (no leakage)" },
  "pl.elo_shift": { vi: "Elo ±", en: "Elo ±" },
  "tag.confident_hit": { vi: "Đúng, tự tin cao", en: "Confident hit" },
  "tag.hit": { vi: "Đúng", en: "Hit" },
  "tag.near_miss": { vi: "Trượt sát", en: "Near miss" },
  "tag.upset": { vi: "Bất ngờ", en: "Upset" },
  "tag.big_upset": { vi: "Đại địa chấn (model cho <15%)", en: "Big upset (model gave <15%)" },
  "pl.f_ht_swing": { vi: "lật kèo sau H1", en: "result flipped after HT" },
  "pl.f_absence": { vi: "vắng trụ cột (đã trừ Elo)", en: "key absence (Elo penalty applied)" },
  "pl.token_prompt": { vi: "Nhập admin token:", en: "Enter admin token:" },
  "pl.token_bad": { vi: "Token sai hoặc backend chưa cấu hình ADMIN_TOKEN.", en: "Invalid token, or backend has no ADMIN_TOKEN configured." },
  "pl.logout": { vi: "Thoát admin", en: "Exit admin" },
  "pl.usage": { vi: "Hành vi người dùng", en: "User behaviour" },
  "pl.usage_totals": { vi: "{v} người dùng · {e} sự kiện (toàn thời gian)", en: "{v} visitors · {e} events (all time)" },
  "pl.daily": { vi: "Người dùng & sự kiện theo ngày (14 ngày)", en: "Daily visitors & events (14 days)" },
  "pl.visitors": { vi: "Người dùng", en: "Visitors" },
  "pl.events": { vi: "Sự kiện", en: "Events" },
  "pl.top_tabs": { vi: "Tab được xem nhiều", en: "Most viewed tabs" },
  "pl.top_matchups": { vi: "Cặp đấu được dự đoán nhiều nhất", en: "Most predicted matchups" },
  "pl.lang_split": { vi: "Ngôn ngữ", en: "Language" },
  "pl.no_usage": { vi: "Chưa có dữ liệu hành vi — sẽ tích lũy khi user dùng app.", en: "No usage data yet — accumulates as users browse." },

  // AI chat
  "chat.title": { vi: "Football AI Analysis", en: "Football AI Analysis" },
  "chat.greeting": {
    vi: "Xin chào! ⚽ Tôi là chuyên gia phân tích AI của World Cup 2026. Hỏi tôi về dự đoán, tỉ lệ, kèo, đội hình — tôi trả lời bằng số liệu thật từ model. Bạn có 5 câu hỏi mỗi ngày!",
    en: "Hi! ⚽ I'm the AI analyst for World Cup 2026. Ask me about predictions, odds, lineups — I answer with real model data. You get 5 questions a day!",
  },
  "chat.greeting_live": {
    vi: "🔴 Đang có trận live! Hỏi tôi về diễn biến, xác suất thắng thay đổi thế nào, hoặc bất cứ trận nào khác.",
    en: "🔴 A match is LIVE now! Ask me about it — or any other fixture.",
  },
  "chat.placeholder": { vi: "Hỏi về trận đấu, tỉ lệ, kèo…", en: "Ask about matches, odds, predictions…" },
  "chat.thinking": { vi: "Đang phân tích…", en: "Analyzing…" },
  "chat.quota_out": {
    vi: "⚡ Bạn đã dùng hết 5 câu hôm nay. Quay lại ngày mai nhé! Trong lúc chờ, khám phá tab Dự đoán trận & Tỉ lệ kèo.",
    en: "⚡ You've used all 5 questions today. Come back tomorrow! Meanwhile, explore the Match Sim & Odds tabs.",
  },
  "chat.error": { vi: "Có lỗi khi kết nối AI — thử lại sau nhé.", en: "AI connection error — please try again later." },
  "chat.disclaimer": { vi: "Tham khảo thống kê — không phải khuyến nghị cá cược", en: "Statistical reference — not betting advice" },
  "chat.chip_deep": { vi: "Phân tích sâu trận {m}", en: "Deep-dive {m}" },
  "chat.chip_value": { vi: "Soi kèo value hôm nay", en: "Find today's value bets" },
  "chat.chip_title": { vi: "Đội nào dễ vô địch nhất?", en: "Who's most likely to win it all?" },
  "chat.chip_whatif": { vi: "Nếu {m} có kết quả sốc thì sao?", en: "What if {m} ends in a shock?" },
  "chat.fab_label": { vi: "Hỏi AI", en: "Ask AI" },
  "chat.teaser": { vi: "👋 Hỏi tôi về bất kỳ trận đấu nào — dự đoán, kèo, kịch bản!", en: "👋 Ask me about any match — predictions, odds, what-ifs!" },

  // common
  "common.loading": { vi: "Đang tải…", en: "Loading…" },
  "common.date": { vi: "Ngày", en: "Date" },
  "common.match": { vi: "Trận", en: "Match" },
  "common.predicted": { vi: "Dự đoán", en: "Predicted" },
  "common.actual": { vi: "Kết quả", en: "Actual" },
  "common.home": { vi: "Nhà", en: "Home" },
  "common.away": { vi: "Khách", en: "Away" },
  "common.draw": { vi: "Hòa", en: "Draw" },
};

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: "vi", setLang: () => {},
});

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(
    () => (localStorage.getItem("lang") as Lang) || "vi");
  useEffect(() => localStorage.setItem("lang", lang), [lang]);
  return <LangCtx.Provider value={{ lang, setLang }}>{children}</LangCtx.Provider>;
}

export function useLang() {
  return useContext(LangCtx);
}

/** t("key", {placeholder: value}) — falls back to the key itself if missing */
export function useT() {
  const { lang } = useContext(LangCtx);
  return (key: string, vars?: Record<string, string | number>) => {
    let s = DICT[key]?.[lang] ?? key;
    for (const [k, v] of Object.entries(vars ?? {})) {
      s = s.replaceAll(`{${k}}`, String(v));
    }
    return s;
  };
}

/** Localized W/D/L word given a side key and the two team codes */
export function outcomeLabel(
  side: string, home: string, away: string, lang: Lang): string {
  if (side === "draw") return lang === "vi" ? "Hòa" : "Draw";
  return side === "home" ? home : away;
}
