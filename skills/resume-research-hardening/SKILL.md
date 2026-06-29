---
name: resume-research-hardening
description: Session handoff contract from 2026-06-22. Resumes the anti-overfitting hardening of the backtesting pipeline. Invoke at the very start of the next session before doing anything else — reads current state, confirms what landed, and continues the two incomplete implementation tracks.
version: 1.0.0
---

# /resume-research-hardening

Session handoff from 2026-06-22. Run this at the start of the next session.

---

## Step 1 — Verify what landed

Run this first to confirm the two committed tracks are actually in the codebase:

```bash
git log --oneline | head -8
# Expect: dcacced feat(research): extend backtest data window to 180d via Alpaca historical API
# Expect: d568fe4 fix(infra): watchdog tz bug + raise orchestrator RAM to 90% + BT divergence analysis

# Confirm data module exists
python -c "from backtesting.data import fetch_bars; print('OK')"

# Confirm lookback flag works
python scripts/backtest_broad_sweep.py --help | grep lookback
```

If either check fails, something was lost — investigate git log before proceeding.

---

## Step 2 — Run inter-day health check

Before writing any code, check that overnight paper trading ran cleanly:

```bash
python scripts/system_health_check.py
python -m live_trading.eod_report
```

Check for CRITICAL errors or missed trading windows (gaps > 15 min during 06:30–13:00 PT in signals JSONL). If the health check shows Overall: ERROR, address that before implementing new features.

---

## Step 3 — Implement Track A: Walk-forward validation

**Why:** Backtest WR was uniformly 68–73% across all 9 strategy classes — that tight clustering signals period-specific parameter fitting on a 60-day window, not real edge. Walk-forward validation splits the data so parameters are never selected on the same bars they are evaluated on.

**File:** `scripts/backtest_broad_sweep.py` — grid-search and AC gate section only. Do NOT touch `_fetch_one` or `main()` argument parsing (Track 1 owns those — already committed).

**What to build:**

For every (symbol, strategy, params) combination that passes the existing in-sample AC gate:

1. Split bars: `split = int(len(bars) * 0.8)` → `train_bars`, `oos_bars`
2. Run the existing grid search on `train_bars` only
3. Take best-params from training, run once on `oos_bars`
4. OOS must pass: WR ≥ 50% AND expectancy ≥ 0.10%/trade AND n ≥ 5 trades
5. Only both-gate entries enter `universe_ac_passes.json`
6. Add `oos_wr` and `oos_expectancy` fields to each entry; flag `oos_skipped: true` when OOS window < 200 bars

**CLI flag:** `--no-wfv` disables OOS gate (backward compat). WFV is ON by default.

**Progress output:** `[WFV] AAPL RSIOversoldMR: IS WR=74.2% OOS WR=61.3% — PASS`

**Commit:** `feat(research): walk-forward validation gate in broad sweep (IS 80% + OOS 20%)`

**KNOWLEDGE.md:** Add Decisions row (2026-06-22) documenting WFV gate and OOS thresholds.

---

## Step 4 — Implement Track B: Min-hold exit + bid-ask spread

**Why:** Win/loss ratios of 0.56–0.62x on RSI/SVWAP strategy classes means exits fire too early on winners. Adding a minimum hold forces the position to ride the mean-reversion longer before a signal exit is allowed. Bid-ask spread not being modeled inflates BT WR by ~3–5%.

**Files:** `backtesting/strategies.py` and `backtesting/sim_core.py` only. Do NOT touch `live_trading/` strategy classes.

### Part A — Min-hold exit guard

Add `min_hold_bars: int = 3` to these classes ONLY (low w/l ratio group):
- RSIOversoldMeanReversion
- SessionVWAPVixMR
- SessionVWAPMeanReversion
- SessionVWAPVolumeMR
- TripleConfirmMeanReversion

Do NOT add to: MeanReversionCombo, BollingerBandsMeanReversion, VWAPMeanReversion, SessionVWAPToDMR (already near-symmetric w/l).

In each exit check:
```python
if bars_held < self.min_hold_bars:
    continue  # skip signal exit
```

Sweep grid values: `[0, 3, 6]` — so the optimizer finds optimal minimum hold per symbol.

Add `min_hold_bars` to `scripts/generate_live_registry.py` class→param mapping.

Assert `min_hold_bars < max_hold` for any strategy entry.

### Part B — Bid-ask spread cost

In `backtesting/sim_core.py` PnL calculation, add `spread_cost_pct: float = 0.0001`:
```python
effective_entry = entry_price * (1 + spread_cost_pct)
effective_exit  = exit_price  * (1 - spread_cost_pct)
```

Add `--spread-cost FLOAT` CLI flag to sweep script (default 0.0001). `--spread-cost 0` = identical to pre-change behavior.

**Tests:** `pytest tests/ -x -q` must pass. Fix failures before committing.

**Commit:** `feat(backtesting): min_hold_bars exit guard + bid-ask spread cost model`

**KNOWLEDGE.md:** Add Decisions row (2026-06-22) for both Part A and Part B.

---

## Step 5 — Integration smoke test

After both tracks commit:

```bash
# Verify all three switches compose cleanly
python scripts/backtest_broad_sweep.py --symbols AAPL --lookback-days 180 --no-wfv --spread-cost 0
# Should reproduce pre-change behavior

python scripts/backtest_broad_sweep.py --symbols AAPL --lookback-days 180
# Should run full IS/OOS pipeline with Alpaca data
```

---

## Background context

**Root cause:** Full analysis at `docs/PAPER_VS_BACKTEST_ANALYSIS_20260622.md`. Short version: 60-day training window + no OOS split + signal-based exits that cut winners early + bid-ask spread not modeled = all nine strategy classes showing 8–35% BT→paper WR gap.

**What's already done (do not redo):**
- `backtesting/data.py` — `fetch_bars()` using Alpaca historical API for 180d bars. Yahoo's 60-day cap is server-side and hard; stitching doesn't work.
- `scripts/backtest_broad_sweep.py` — `--lookback-days N` flag, default 180.
- `multiframe_runner.py` — watchdog timezone fix (no more offset-naive subtract error).
- `data/orchestrator_config.json` — RAM threshold raised to 90%.

**Open design decision still needing user input:** EOD force-close (`EOD_FORCE_CLOSE=1` in `services.ps1`). Enabling closes all positions at market close; disabling lets `max_hold_cb` carry them overnight. Not blocking implementation work — ask user before changing.
