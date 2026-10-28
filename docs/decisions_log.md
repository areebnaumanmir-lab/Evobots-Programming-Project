# Decisions log

Running record of what we have agreed. It references question numbers in decision_questions.md.

## Round 1 (2026-09-26)

| Q | Decision | Status |
|---|---|---|
| Q1 | **Changed scope.** This is a portfolio project to learn and demonstrate current Operations Research / Financial Engineering. Success means a *natural-selection* engine that is as close to the real world as possible: bots have simulated money, **die when they lose too much**, and can trade **futures, options and swaps**. It generates bots, **scores how deployable they are**, and can **deploy** them. Priority 1 is the quality and speed of selection in producing a viable bot. Priority 2 is long (multi-week) training runs that maximise profit. | Stated by user |
| Q4 | Delegated to me. Proposal below. | Proposed |
| Q5 | Not answered yet | Open |
| Q15 | Repo/zip + `uv` lockfile. Internet is fine on first install for packages; market data must never need a connection. | Agreed |

## What the new scope changes in the draft spec

1. **Bots become accounts, not signals.** Each bot holds cash, positions and margin. It pays fees, funding and financing, and is liquidated when equity falls below maintenance margin. "Death" is a real mechanism, not a fitness penalty. The spec's §7 maths becomes an account/margin engine.
2. **Selection becomes literal natural selection.** Survival and wealth growth drive reproduction. This links the empirical papers (rule discovery) to the ecology papers (Farmer, Lo, Chen & Yeh).
3. **Multi-instrument.** Futures (margin, multipliers, expiry/roll), swaps (perpetual swaps with funding, and/or interest-rate swaps priced off a yield curve), and options (need a pricing and implied-volatility model unless real option quotes are available).
4. **Deployability is its own module:** out-of-sample survival probability, drawdown and ruin statistics under resampled paths, stability across seeds and regimes, cost/slippage sensitivity, and multiple-testing-adjusted Sharpe. A **deployment adapter** is separate from the core (paper trading first).
5. **Speed and search quality move to the front.** Vectorised or GPU population evaluation, evaluation-budget allocation (racing / successive halving), multi-objective and quality-diversity search. Q10 (own engine) and Q14 (Python + NumPy) need revisiting. Evaluating the population on the RTX 4060 becomes attractive.
6. **Multi-week runs** need checkpoint/resume, an archive of the best bots found so far, and protection against the obvious risk: longer optimisation on the same history increases overfitting unless the data window rolls forward.

## Proposal for Q4 (to confirm)

**Primary market: crypto derivatives on minute bars**, using Binance's public bulk data. It is keyless, served as zip files with SHA-256 checksum files, and covers spot plus USD-margined and coin-margined futures. An `option` section also exists. The reasons:
- It is the only free source I know of that offers **futures and perpetual swaps together, at minute resolution, for years**, which is also where "huge data" becomes real.
- **Paper deployment** is possible against an exchange testnet or a paper account, which satisfies "ability to deploy".
- **Still to verify before relying on it:** funding-rate history coverage, how far back option data goes, and the redistribution terms for bundling a sample.

**Secondary (for rates/swaps and for a replication):** Fed H.10 daily FX + H.15 Treasury yields (US-government releases) for an interest-rate-swap book and a Neely et al. replication.

**Options:** unless the option data proves adequate, options are **priced synthetically** (e.g. Black-Scholes/Black-76 on a volatility estimated from the underlying). This is a stated modelling assumption, and the report will flag it.

## Round 2 (2026-09-26)

| Question | User's answer | Decision (details in design_spec_draft.md v2) |
|---|---|---|
| Deployment without a broker | "Decide whatever is best; I don't have a broker." | Four deployment levels. **L0** forward test on new data files. **L1** *paper-live*: the bot runs in real time on the exchange's **public, keyless** market-data stream against a local paper broker that uses the same rules as the simulator. **L2** optional exchange-testnet adapter (free testnet key). **L3** real account: interface only, out of scope. No broker is needed for L0–L1. |
| Multi-week training, laptop not on 24/7 | "Train for a few weeks… unsure, can't keep laptop on." | **Interruptible sessions.** `evobots run --hours N` and `evobots resume`, with checkpoints every ~10 min (archive + RNG state), so results are identical however the run is split. Budgets are counted in *evaluations*, not wall-clock. MAP-Elites is an anytime algorithm, so a usable archive exists after every session. A guard against overfitting that grows with compute: the deflated Sharpe uses the true evaluation count, and the sealed hold-out is opened only once. |
| Realism | "Make it realistic." | Exchange simulator modelled on USD-margined perpetual-futures rules: mark-price liquidation, tiered maintenance margin, maker/taker fees, funding at the actual recorded intervals, lot/tick sizes, latency. **Two fidelities:** a bar-level simulator with a depth-calibrated impact model for evolution, and a tick-level trade-replay simulator for promoted bots. |
| Showcase method | "Quality-Diversity search (MAP-Elites)" | MAP-Elites core (grid for 2-D, CVT for more descriptors), with re-evaluation to handle noisy fitness. The optional later emitter is CMA-MAE for continuous parameters. |
| Q4 market (delegated) | – | **Confirmed after probing the data**: Binance USD-M perpetuals (see the verified-data table in spec §4). |
| Q5 data size (delegated) | – | Evolution universe of ~10 liquid perps × 1-min × 2020–present ≈ **1.1 GB** as float32 columns (fits in RAM). The tick layer (aggTrades) is **~6 GB/yr zipped for BTC alone** and is streamed out-of-core, used only for promoted bots. |

## Round 3 (2026-09-26): proposals in round3_market_and_survival.md

| Topic | User's input | Proposal (pending confirmation) |
|---|---|---|
| Map | "Whatever can be realistically done" | Holding period (log, 1 day to 1 year) × directionality (P&L correlation with front month). Leverage is handled by the fitness, not by an axis. |
| Training time | Variable; weeks should be *possible*; a deployable bot at any time | A `deployable/current_bot.json` is refreshed at every checkpoint after a quick deployability check. It falls back to "do nothing" if nothing passes. |
| Death | "When a real trader would stop", with nuance | Five-layer career model: L1 margin, L2 mandate limits, L3 capital-flight hazard calibrated to hedge-fund attrition studies, L4 CUSUM opportunity-cost stop (also catches overspecialisation), L5 peer rank. The hazard enters fitness as an expected survival probability, not as random deaths. |
| Market | Doubts about crypto futures; wants a focused, realistic market | **Proposed switch to US energy futures** (WTI first), daily. Verified EIA contract 1–4 prices 1983–2024-04-05, weekly inventories to 2026-09, CFTC COT positioning. Crypto becomes an optional second market for execution-realism experiments. |
| Risk | QD plus baselines; risk should be punished automatically | Baselines: do nothing, minimum size, passive long, 12-month trend, carry, random bots. Fitness: expected excess log-growth under the career model, which punishes over-leverage by itself (zero excess growth at 2× Kelly). QD gives visibility across styles, not protection. |
## Round 4 (2026-09-26): market decided; details in round4_electricity_virtual_trading.md

| Topic | User's input | Decision / proposal |
|---|---|---|
| Meaning of "not previously optimised" | A market not covered by the surveyed papers and GitHub projects | Survey coverage: FX, stocks, crypto, one equity-index-futures repo. No electricity. |
| Market | **"Do electricity virtual trading"** (decided) | Supersedes the round-3 energy-futures proposal. Proposed: **MISO** as primary (keyless daily CSVs, 2,414 nodes, from 2023-01-01, verified), CAISO as possible second market. |
| Bot output | – | Proposed: per (node, hour), side INC/DEC + limit price + MW. P&L = cleared × q × direction × (RT − DA) − fees (admin + RSG uplift). |
| Map | – | Proposed: net direction (DEC − INC share) × selectivity (fraction of node-hours traded). Holding period is no longer an axis. |
| Look-ahead | – | Decision at DA close (D−1 10:30 ET [verify]); may use DA ≤ D−1 and RT ≤ D−2 only. |
| Data size | – | Hubs 2.1 MB; all nodes LMP DA+RT 632 MB; all components 1.9 GB; raw CSV ≈ 3.3 GB. Bundle hubs + load zones; optional one-command build of a memory-mapped nodal store. |

## Round 5 (2026-09-26): details in round5_iso_universe_history.md

| Topic | User's input | Decision / proposal |
|---|---|---|
| MISO vs CAISO | Agent's discretion, with detailed reasoning | **Decided: MISO primary.** It has 0 of 8 virtual-bidding papers vs CAISO's 5, and one all-node file per day. A CAISO adapter comes later: a benchmark against published results, a market found less efficient (2104.02754), and a fallback if MISO retires public files. |
| Location universe | Wants options with reasons | Options A hubs / B hubs + load zones / C all nodes / D clustered representatives / E staged A→D→C. **Recommended: E.** |
| History depth | Asked for the literature | The literature uses 3–6 years with ~1-year rolling training. MinBTL (Bailey et al. 2014) limits independent trials: 3.2 in-sample years allow 15 at Sharpe 1 and 3,265 at Sharpe 2. **Recommended:** MISO 2023+ plus forward-growing data plus stress scenarios, NYISO later. Report effective trials and the deflated Sharpe ratio. |

## Round 6 (2026-09-26): details in round6_miso_history_holdout.md

| Topic | User's input | Decision / proposal |
|---|---|---|
| ISO order | **Decided:** MISO first, CAISO second | – |
| Location universe | **Decided:** option E (hubs → clustered representatives → all nodes) | – |
| History | 3.7 years is fine, but wants a 12-month hold-out and older MISO data to compensate | Found keyless MISO monthly archives back to **2005-04** (observed). Proposed: train from **2015-03** (uniform format, 10.6 in-sample years); keep 2005-04 → 2015-02 for stress scenarios and a robustness check only. |
| Sealed hold-out | **Decided:** 12 months | 2025-09-22 → 2026-09-21, stored separately, scored once per finished run, every opening logged. |

## Round 7 (2026-09-26): details in round7_consistency_and_shocks.md

| Topic | User's input | Decision / proposal |
|---|---|---|
| History | **Decided: option D** (2005-04 onward) | Evolution 2005-04-01 → 2025-09-21; hold-out 2025-09-22 → 2026-09-21 |
| Consistency | Data must draw from the same places | 387 locations persist under the same name across 6 snapshots, 2005–2026 (3 hubs + CINERGY/INDIANA). Proposed: fixed persistent universe (~583 MB). Information inputs limited to series covering 2005–2026: prices, Henry Hub spot, GPR, EPU, calendar. MISO load forecasts (2015+ only) and EIA gas futures (end 2024-04) excluded. |
| Shocks | Avoid them, or inform bots as real traders would be | The 2026 Iran war (from 2026-02-28) is inside the hold-out, so avoiding shocks is not viable. Proposed: mechanical GPR + EPU indices as bot inputs, and a hand-written event calendar for reporting only. |
| Bundle | Hub prices "2025-2026" (read as 2005–2026, to be confirmed) | – |

## Round 8 (2026-09-26): details in round8_universe_shocks_weather.md

| Topic | User's input | Decision |
|---|---|---|
| Locations | **Decided:** whatever exists on each day | Yearly price files with a per-year location index (≈ 3.2 GB of LMP). Bots choose locations by past-data properties, never by name. Virtual bids last one day, so locations appearing or disappearing strand no positions. |
| Shocks | **Delegated** | **Decided by agent:** GPR + EPU + Henry Hub as lagged bot inputs; the named-event calendar is for reporting only. Known limit: index revisions are unobservable. |
| Weather | **Decided:** include forecasts if possible | Found NWS Point Forecast Matrices at IEM, 2005–2026, for 9 offices covering MISO hubs (observed). Fetch once (~1.4 GB), bundle the parsed table (~16 MB). ASOS observations for reporting only. GFS MOS set aside (only from 2007-05). |
| Bundle | **Decided:** hub prices 2005–2026 | – |

## Round 9 (2026-09-26): details in bot_inputs_and_representation.md

| Topic | User's input | Decision |
|---|---|---|
| Bot representation | Asked how bots understand inputs and news text | Proposed: 25 hand-built point-in-time features; a fixed bot skeleton (where/when/score/side/price/size/risk); typed GP formulas of at most ~15 nodes; MAP-Elites selection with a rolling window. Text reaches bots only as GPR/EPU article-count indices. No LLM reading of articles, because models trained later would leak hindsight. |
| Feature units | **Decided:** raw units | Unit-typed formulas; constants drawn from each feature's historical range |
| Feature count | **Decided:** stay at 25 | – |
| Weather link | **Decided:** accepted (location → most-correlated hub over the past 365 days → NWS office) | – |

## Round 10 (2026-09-26): bot_inputs_and_representation.md §1.7

| Topic | User's input | Proposal (pending) |
|---|---|---|
| Energy relevance of threats | Only energy-related threats matter to MISO | Observed: in the Iran war, WTI rose 42 % (Feb→Mar 2026) while Henry Hub fell 16 %; US gas peaked at $30.72 on 2026-01-23, before the war. Replace `gpr` with `gas_vol_20d` (Henry Hub realised volatility). GPR becomes reporting-only. `epu` kept on probation. Oil excluded. |
| New projects / innovation | Wants regional project information | EIA-860M (keyless, monthly) lists every generator with operating/retirement dates and lat/lon. MISO rebuild: wind 1.3→33.7 GW, solar 0→24.4 GW, coal 71.1→47.5 GW (2005-04→2026-08). Add `wind_cap_region` and `solar_cap_region`, replacing `month` and `loc_age_days`, so the total stays 25. Planned projects (monthly snapshots only from 2016) go to reporting only; no consistent transmission dataset. |

## Round 11 (2026-09-26)

| Topic | User's input | Decision |
|---|---|---|
| EPU | **Decided:** keep | – |
| US gas | **Decided:** include | `gpr` → `gas_vol_20d` accepted; gas_price, gas_chg_5d and gas_vol_20d are all inputs |
| Global gas supply shocks | Asked (e.g. Qatar) | Agent: not a bot input. World Bank monthly: in 2022 Europe gas peaked at 14.6× its 2019 level, US at 3.4×; month-to-month correlation of US with Europe is 0.16 (2010–2025). Global prices go to reporting. |
| `month`, `loc_age_days` | Unclear to the user | Explained; the swaps to `wind_cap_region` / `solar_cap_region` await confirmation |

## Round 12 (2026-09-26): design spec v3

| Topic | User's input | Decision |
|---|---|---|
| Feature swaps | **Decided:** accept both | `month` → `wind_cap_region`, `loc_age_days` → `solar_cap_region`. The final 25 are listed in design_spec_draft.md §6. |
| Spec | – | Rounds 3–12 consolidated into design spec v3. Open: the default career preset (proposed: hedge fund) and the M0 [verify] list. |

## Round 13 (2026-09-27): design spec v3.1 §8

| Topic | User's input | Decision |
|---|---|---|
| Career preset | **Decided:** individual is the focus; prop trader and hedge fund are options | Individual = a one-person company meeting MISO's minimum capitalization ($500k tangible net worth per a filing citing Attachment L; a blog says $1M; verify at M0). Death when equity < floor. Quit hazard calibrated to day-trader survival (44/24/15 % at 1/2/3 years, Barber et al. 2020). CUSUM against risk-free plus fixed costs. Peers off. Default capital $1M (proposed). |

## Round 14 (2026-09-28): starting capital, evobots/docs/capital_sizing.md

| Topic | User's input | Decision |
|---|---|---|
| Starting capital | Must be configurable, with a data-based default and bounds | **Default $1.5M, range $250k–$5M (Stage A)**, in `CapitalSettings`: TOML `[capital]`, CLI flags, HTML explorer |
| Sizing rule | Delegated | position_scale = min(1, daily_risk_budget × equity / p99 full-size daily loss); budget 2 %; full size reached at $1.39M |
| Liquidity cap | – | min(5 MW, 5 % of the hub's median cleared virtual MW) per hub-hour: 5 MW at seven hubs, 4 MW at MS. Volumes from MISO's cleared-bids report, attributed by unique ex-ante price. |
| Leverage | Flag | Separate setting: `daily_risk_budget` is the leverage-like knob. MISO collateral (MWh limit × MPD $12 × 2 days) is only $22k at full Stage A size, versus a $492k worst day, so equity must be marked daily. `credit_share` is kept for stages D and C. |
| Individual floor | – | MISO Minimum Participation Requirements: >$1M net worth or >$5M assets (checked). The default $1M in spec v3.1 was therefore raised. |

## Round 15 (2026-09-28): review of the capital analysis, capital_sizing.md sections 2b, 4b, 5, 6, 9

| Topic | User's input | Result |
|---|---|---|
| $0.59/MWh | Doesn't reconcile with full volume ($0.15) | Corrected: it divided by cleared MWh with an **assumed** 25 % cleared share of hub-hours (one overall number). Full volume gives $0.146; the measured hub clearing rate (72.1 %) gives $0.203. Fixed-cost floors: $204k / $283k / $817k; bots clearing < 14.6 % of hub-hours never get below $1/MWh. |
| $1.5M as the lowest step | Check under both interpretations | **Not** the lowest step under the four conditions: $1.05M in all interpretations (the $1M floor binds). $1.5M relies on a fifth, now explicit, condition, tail headroom: the lowest step is $1.40M with point-in-time sizing ($1.35M with full-sample). **Default kept at $1.5M for margin; $1.40M is the data minimum; the user decides.** |
| Clearing | Explain the assumption | The simulator fills a bid fully iff its limit meets the DA LMP. Measured: the rule predicts 99.5 % (market) / 100.0 % (hubs) of cleared status; others' bids clear 48.8 % [46.1, 51.4] market-wide and 72.1 % [70.7, 73.5] at hubs. The bot's rate is an output. |
| Look-ahead | Is the scale a constant? | It was a full-sample constant, used only in the calibration, CLI and explorer; no backtest existed. Now: `sizing.py` trailing 365 days, newest usable day D−6, 90-day warm-up with no trading; the constant is renamed CALIBRATION_ONLY and a test keeps it out of simulation code. Trailing C_full $0.52M–$2.24M; p99 exceeded on 2.2 % of days. 2 % budget kept. 9 new tests (23 total). |

## Round 16 (2026-09-28): capital_sizing.md sections 6b, 7b, 7c, 10, 11

| Topic | User's input | Result |
|---|---|---|
| Default capital | **Decided:** keep $1.5M for now | Justified without the MISO rule: headroom 33.3 % vs worst 20-day loss 24.6 %; full size on 80.6 % of days |
| MISO $1M rule | Confirm with document and section | **Confirmed:** Attachment L v56.0.0 (eff. 2024-06-03) §III.B, net worth > $1M or assets > $5M, one of 7 routes. Earlier wording "requires" corrected. |
| Ruin floor | Separate setting; absolute vs relative | **Relative by default** (`ruin_floor_fraction` = 2/3); optional absolute `ruin_floor_usd`; absolute floors leaving under 10 % headroom are rejected. At $250k / $1.05M / $5M: floor $167k / $700k / $3.33M; worst 20-day loss 50.4 / 34.5 / 8.2 % vs 33.3 % headroom. Lowest passing step: $1.10M. |
| Storm sensitivity | Helper with and without named storms | `storms.py`. Always-INC at $1.5M: F 0.540 → 0.684 without storms (Elliott −0.212, Uri +0.069). |
| Size gene | Propose | g ∈ [0.05, 1] × position_scale × cap; sizing must move to the bot's own trailing p99 (mixed-direction tail 1.56×). Not added: F rises monotonically in g for always-INC, so the gene is likely to saturate. Tests first. |
| 936 vs 960 | Pick one, add a test | **936 is right** (MS.HUB 4 MW). The CLI now uses per-hub caps; tests check the CLI, settings and volume table against each other. |
| Explorer | Expected values | At $1.5M / $1.05M / $5M (section 10); caps now rounded to 0.1 MW |
| Pre-2019 check | Optional | 2015-03 → 2018-12 fetched (MS.HUB from 2017-12). Breach rate 1.38 % (2015–18) vs 2.12 % (2019–25). 2005–2014 not checked. |

## Round 17 (2026-10-23): M0 kickoff in Claude Code; rounds/round17_m0_kickoff.md

| Topic | User's input | Decision |
|---|---|---|
| UI editing language | **Decided:** A | FastAPI + Jinja2 + one `theme.css`, no build step |
| Offline scope | **Decided:** (a) | offline once installed; first install may download packages |
| Single-file deliverables | "The exported bots should work independently of source code." | exported bots are standalone standard-library files with an equivalence test; the engine `.pyz` question is asked at M9 |
| Performance targets | **Decided:** accepted | `CLAUDE.md` §14.3 |

## Round 18 (2026-10-23): MISO rules; market_rules.md, rounds/round18_m0_market_rules.md

| Topic | User's input | Result |
|---|---|---|
| Contact email | Supplied | stored only in the git-ignored `config/local.toml` |
| M0 [verify] list | – | resolved from 13 MISO/IMM/FERC documents: deadline 10:30 EPT since 2016-11-05 (11:00 EST before); preliminary RT not archived; fee and RSG mechanics and netting; three RSG eras; collateral formula and $12 MPD floor; minimum capitalization $500k TNW or $200k security (non-FTR); Attachment L v57.0.0 identical for virtuals. Open: rate history (Rates Factors file), IMM volume limits |
| Decision time, holiday rule, placeholder fees | – | proposed D1–D3 (decided round 20) |

## Round 19 (2026-10-23): review against 20 questions; rounds/round19_prompt_review.md

| Topic | User's input | Decision |
|---|---|---|
| Death | **Decided:** default is running out of money | other career layers optional, off by default |
| Code, best bot, sealed test | **Decided:** obvious buttons | View code, Best bot, Final test, Refine, Forward test |
| UI separation, documentation | **Decided** | import test; change ledger; every function and constant documented |
| Trader as organism, lineage, reproduction, Life mode | Asked | proposed; decided in round 20 |

## Round 20 (2026-10-24): literature, fixes, data, style; rounds/round20_literature_data_style.md, design_rationale.md

| Topic | User's input | Decision |
|---|---|---|
| Fix earlier decisions | **Delegated:** "NOW is the time to fix any of the previous decisions" | 5-year training window; elites re-evaluated when the window moves; trader/genome/behaviour ids; PTC2 start with a no-founder control; size-fair crossover, iso+line-DD, bandit operators, neutral skip; code ⇄ genome round trip; language-model mutation rejected; R19-1…6 and D1–D3 decided |
| Data | **Decided:** download the MISO archive | DA/RT for every location 2005-04-01 → 2026-10-24 downloaded and parsed; hold-out stored apart |
| Visual style | **Decided:** reference image, simpler, less colour, words not boxes | white, hairlines, ink + one signal red; `docs/design/theme.css` |

## Round 21 (2026-10-24): decisions log, capital_sizing.md and calibration CSVs received; rounds/round21_reconciliation.md

| Topic | User's input | Result |
|---|---|---|
| Decisions log, `capital_sizing.md`, `capital_sweep.csv`, `headroom_trailing.csv`, `hub_price_stats.csv` | Uploaded | added to `docs/` and `docs/data/` |
| Reproduction | – | **all 176 values** of `hub_price_stats.csv`, the 12 benchmark P&L numbers of §4 and the trailing-p99 table of §4b (with the 2.16 % breach rate by year) reproduced exactly from the round-20 archive (`tools/check_against_claude_science.py`) |
| Reconciliation | – | `design_rationale.md` Part C rewritten from this log: 14 round attributions corrected, 7 missing decisions added; no conflicts with the briefing |

## Round 22 (2026-10-24): build independently; rounds/round22_independent_build.md

| Topic | User's input | Result |
|---|---|---|
| Missing files | **Decided:** "make the project independently and ask all the questions you need directly here" | missing files are rebuilt from the briefing and docs and proven against recorded numbers; questions asked directly |
| Capital slice | – | rebuilt from `capital_sizing.md`; 133 tests reproduce every recorded number (trailing p99 on all 2,456 days, breach rates, sweep, headroom, fixed-cost floors, storms) |
| Naming | – | `daily_risk_budget_fraction`, `credit_share_fraction`, `liquidity_share_fraction` (§14.1); floors off by default; MPD no longer a setting |

## Round 23 (2026-10-24): weather offices, cleared bids, pacing; rounds/round23_m0_data_and_pacing.md

| Topic | User's input | Result |
|---|---|---|
| Hub → NWS office | **Decided:** nearest-load rule (recommended) | MINN→MPX, MICHIGAN→DTX, INDIANA→IND, ILLINOIS→ILX, ARKANSAS→LZK, MS→JAN, LOUISIANA→LIX, TEXAS→LCH; LOT feeds no hub |
| Cleared bids | **Decided:** every day (recommended) | 2023-01-01 → newest (≈90-day publication lag), with DA ex-ante prices; ~5 GB |
| Weather fetch | **Decided:** start now (recommended) | `tools/fetch_nws_forecasts.py` running, ~8 h |
| Pacing | **Decided:** continue, stop at check-ins (recommended) | stop only at the §2.4 check-ins; questions asked as they come up |

## Round 24 (2026-10-24): M0 finished; rounds/round24_m0_finish.md

| Topic | User's input | Result |
|---|---|---|
| Capital explorer | – (delegated, R24-1) | static page; every value computed in Python by `capital_summary`, looked up by the page |
| "Well above full size" warning | – (delegated, R24-2) | fires at ≥ 2× the full-size point (assumption) |
| Abbreviations | – (delegated, R24-3) | DC, OPF, PTDF approved for the ORFE power-flow material |
| MISO redistribution | **open** | proposal: build locally, never redistribute, until Areeb reads MISO's terms |

## Round 25 (2026-10-24): MISO's terms; rounds/round25_miso_terms.md

| Topic | User's input | Result |
|---|---|---|
| MISO redistribution | pasted MISO's Terms of Use; "You can, but make it changeable by the user" | **decided:** build locally, never redistribute; switch `is_miso_redistribution_allowed` (default false) at M1 |
| $1.5M default | same answer | **decided:** final default, still the user's choice |
| Scripted MISO access | – | terms forbid "automated means"; cleared-bids fetch stopped at 2026-01-23. **Open:** options A–D, recommendation A + B |
| Rates Factors file, [verify] markers | "tell me how to do it" | instructions given; `docs/verify_register.md` groups the markers for acceptance by group |

## Round 26 (2026-10-24): MISO data kept for private use; M1 starts; rounds/round26_m1_start.md

| Topic | User's input | Result |
|---|---|---|
| Downloaded MISO data | **Decided:** "Keep everything for private use, the fine print says that data is only restricted if you're using it for explicitly commercial purposes" | everything kept, private use only, never redistributed. Claude noted that the pasted Terms of Use contain no commercial carve-out; the source of that reading is [verify]. Scripted MISO downloads stay paused until it is recorded or Areeb says to resume |
| DA file choice | – | `da_lmp` before 2015-03-01 (ELMP go-live), `da_expost_lmp` from then on; the 2015-02-19 ex-post file is not used |
| Hub volumes | – | cleared-bids attribution reproduces `hub_volume_stats.csv` exactly (64/64) |

## Round 27 (2026-10-24): every [verify] marker checked; rounds/round27_verification.md

| Topic | User's input | Result |
|---|---|---|
| Markers | "independently verify all these markers and facts" | K, L, O and almost all of A resolved against primary sources; corrections listed in the round doc. Open: F (fees), P (MPD), the risk-free source, and Areeb's commercial-use source |
| MPD | – | the tariff wording was tested on the full archive and doesn't reproduce MISO's published values; no MPD history can be computed from public data |
| Weather download | "Continue the download" | resumed; relaunched after each 2-hour limit |

## Round 28 (2026-10-28): answers to the round-27 questions; rounds/round28_answers.md

| Topic | User's input | Result |
|---|---|---|
| MISO fee and RSG rates | **Decided:** "I'll download the file" | Areeb downloads the *Market Settlements Rates Factors* workbook and attaches it; saved to `data/inbox/` with its SHA-256. Labelled estimates until then (D3). The MPD stays the $12 floor, labelled "estimate", since the file doesn't contain it |
| Risk-free rate | **Decided:** FRED 3-month T-bill (DTB3) | keyless CSV, Federal Reserve H.15, public domain with citation requested |
| Sunday holiday | **Decided:** Sunday and Monday | D2 confirmed |
| Battery efficiency | **Decided:** 82 % (EIA fleet average) | O4's default round-trip efficiency |
| Hub weather | **Decided:** load-centre town | one fixed forecast town per hub: Minneapolis, Detroit, Indianapolis, Peoria, Little Rock, Jackson, New Orleans, Beaumont; missing town → missing input |
| Plant → hub area | **Decided:** nearest hub town | great-circle distance to the same eight towns; Iowa splits near Des Moines |
| Series timing | – (Claude, D-92) | T-bill, EPU and GPR usable two days after the observation (posting time unknown or after 10:30); gas and oil one business day |
