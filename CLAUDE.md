# evobots: handoff prompt for Claude Code

> **How to use this file.** Paste everything below the line into Claude Code as your first message, or save it as `CLAUDE.md` at the root of the project folder so every session reads it. Before that, put the files from the "Genetic Trading Bots" project into the folder layout in §4. Fill in the one placeholder, `<CONTACT_EMAIL>` in §5.4, or leave it and Claude Code will ask you for it.

---

## 0. Your role and the first thing to do

You are taking over **evobots**, a project I (Areeb) have been designing over 16 discussion rounds in another Claude product (Claude Science) and a planning session in Claude. The design is essentially finished. One thin vertical slice of code exists (capital and position sizing, 40 passing tests). Everything else still has to be built.

This prompt is your full briefing. It contains:
- every decision made so far, and why;
- every data source used, with URLs, formats, quirks and the observed numbers;
- the code that exists;
- the engineering rules;
- the milestone plan;
- the open questions.

Treat it as the source of truth until the repository's own `docs/decisions_log.md` and `docs/design_spec.md` supersede it. When they disagree, ask me which is right.

**Revision history of this briefing** (details in `docs/change_ledger.md`):
- Round 17 (2026-10-23): the four §17.1 decisions answered (§17.1).
- Round 18 (2026-10-23): MISO rules researched; see `docs/market_rules.md`.
- **Round 19 (2026-10-23): reviewed against 20 questions** (`docs/rounds/round19_prompt_review.md`). Changed or added:
  - the trader as an organism with its own generated source code (§9.1);
  - identity, names and lineage (§9.4); founders (§9.5); mutation operators (§9.6);
  - **default death = out of money**, other career layers optional (§10.1);
  - reproduction and selection pressure (§11.2); compute time vs market time and Life mode (§11.3);
  - "best bot" defined (§11.4); Refine runs (§11.5); the grid map explained (§11.6);
  - the sealed test in practice (§12.4);
  - who controls which setting (§13.1); data and input status (§7.0, §8);
  - the change ledger and complete documentation (§14.2); UI separation and visual style (§14.5); app buttons and explanations (§15).
  - Open round-19 choices are in §17.3.
- **Round 20 (2026-10-24): literature review, decisions fixed, data downloaded, visual style.** The logic behind every decision now lives in `docs/design_rationale.md` (a living document; update it with every decision). Changed:
  - training window 1 → **5 years**, and elites re-evaluated when the window moves (§11);
  - trader ids, genome ids, behaviour ids (§9.4); PTC2 start and a no-founder control (§9.5); size-fair crossover, iso+line-DD, bandit operator selection, neutral-child skip (§9.6); code ⇄ genome round trip (§9.1);
  - the round-18 and round-19 open choices decided under my delegation (§17.3);
  - the whole MISO DA/RT archive downloaded and parsed (§3, §7.0, §7.3);
  - the visual style from my reference image (§14.5).
- **Round 22 (2026-10-24): build independently.** My instruction: "make the project independently and ask all the questions you need directly here". Missing files are now **rebuilt from this briefing and the docs**, not waited for (§4). The capital slice is rebuilt from `capital_sizing.md` and reproduces every one of its numbers (133 tests).
- **Round 23 (2026-10-24): weather offices, cleared bids, pacing** (`docs/rounds/round23_m0_data_and_pacing.md`). Hub→office table by the nearest-load rule (§7.4); every day of cleared bids from 2023 (§7.0); the weather fetch started; work continues milestone by milestone and stops only at the §2.4 check-ins.
- **Round 24 (2026-10-24): M0 finished** (`docs/rounds/round24_m0_finish.md`). Capital explorer rebuilt with every value computed in Python and tested in a headless browser; naming test; benchmarks; Markdown doctests; O0 DC-OPF; redistribution terms (`docs/data_sources.md`: MISO data is build-locally until its terms are read); 173 tests.
- **Round 25 (2026-10-24): MISO's terms** (`docs/rounds/round25_miso_terms.md`). They forbid redistribution and **automated access**. MISO data is built locally and never redistributed (a user switch arrives at M1). Scripted MISO downloads are stopped until I choose between the options there. $1.5M is the final default.
- **Round 26 (2026-10-24):** I keep all downloaded MISO data for private use. New scripted MISO downloads stay paused until the commercial-only fine print I mentioned is recorded or I say to resume (`docs/data_sources.md` §4).
- **Round 27 (2026-10-24): every unchecked-fact marker checked** against primary sources (`docs/rounds/round27_verification.md`).
- **Round 28 (2026-10-28): my answers to round 27** (`docs/rounds/round28_answers.md`): I download the Rates Factors file myself; risk-free rate = FRED DTB3; D2 kept; battery round-trip efficiency 82 %.
- **Round 21 (2026-10-24): decisions log and capital files received.** `docs/decisions_log.md` (rounds 1–16, now extended to 21), `docs/capital_sizing.md`, `docs/data/capital_sweep.csv`, `headroom_trailing.csv`, `hub_price_stats.csv`. Claude Science's calibration numbers are **reproduced exactly** from the downloaded archive (§7.0). `docs/design_rationale.md` Part C was rewritten from the log; no conflicts with this briefing.

**First session, in order:**
1. Read this whole prompt.
2. Take stock of the folder (§4). List what's present, missing or unexpected. Don't move or rename anything yet.
3. Check the environment (§5): Python, uv, git, cores, RAM, GPU, OS, and which of the data domains in §7.9 you can reach.
4. Ask me the four open decisions in §17.1 in one go (multiple choice, recommendation first).
5. Then propose the M0 plan (§16) as a short task list and start on it. M0's research, tooling and naming pass don't depend on my answers.
6. Read §20 (the ORFE track) before designing any interface in M1–M3. Several ORFE modules reuse the simulator, the scenario generator and the report card, so those interfaces must leave room for them from the start.

---

## 1. What the project is

### 1.1 Goal (in my words, from round 1)
"This is a project I'm doing so that I can understand and show proficiency in Operations Research and Financial Engineering's latest developments. What would count as a success is a natural selection algorithm that is as close to the real world as possible (if you lose a certain amount of money you can't go on trading; simulated money, like in the Wharton Investment Challenge). I want it to be a tool to generate trading bots, tell me how deployable they are, and the ability to deploy them. The focus is first on the quality and speed of the natural selection algorithm in making a viable bot, and second it should be able to train on data for a few weeks to make the most profit."

### 1.2 What it became after 16 rounds
A system that **evolves a diverse archive of small, readable trading bots** for **virtual (financial) bidding in MISO**, the US Midwest electricity market (Midcontinent Independent System Operator).
- It judges each bot the way a real trading career would: bots carry simulated money and **die when they run out of money** (round 19 default; optional career layers can make them stop earlier, as a real trader might, §10.1).
- It reports **how deployable** each bot is (a report card with statistical gates).
- It can hand over **a deployable bot at any moment**: the best bot that passes the gates, or "do nothing" if none does.
- The showcase method is **MAP-Elites**, a quality-diversity algorithm that keeps the best bot in each behaviour niche rather than one overall winner.

### 1.3 Why this market (rounds 4–5)
- I asked for a market "not previously optimised", meaning **not covered by the papers and GitHub projects we surveyed**, not "an unexploited niche".
- The survey: 11 papers in my folder (FX, US stocks, simulated markets) and 24 GitHub repos (mostly crypto and stocks, one E-mini futures repo). None trades electricity.
- Of 8 arXiv papers on electricity virtual bidding, **none studies MISO** (CAISO 5, PJM 2, NYISO 2, ISO-NE 1, ERCOT 1), and none uses evolutionary or quality-diversity methods.
- MISO data is free, needs no key, and is large: about 2,000 locations × 24 hours × 21 years.
- I rejected crypto (pumps, whales, no supply-chain fundamentals) and then energy futures (heavily optimised by the managed-futures industry; EIA stopped publishing futures prices after 2024-04-05).

### 1.4 Priorities
1. Quality and speed of selection in producing a viable bot.
2. Long runs (possibly weeks, split into sessions on a laptop that isn't on 24/7) that keep improving profit, with a usable bot after every session.
3. Realism, honesty about overfitting, and code I can read and edit.
4. **ORFE relevance (added 2026-10-23).** The project should show Operations Research and Financial Engineering methods, not only evolutionary computation: optimization under uncertainty, stochastic modelling, risk measures, sequential decisions, and rigorous statistics. §20 adds an "ORFE track" of modules that sit next to the evolutionary engine, use the same data and simulator, and are compared against it. Scope is not a concern; build all of it, in the order given in §20.10.

---

## 2. How we work together

### 2.1 The round loop (keep it; it caught real bugs, e.g. a look-ahead in round 15)
For every substantive decision or milestone:
1. Propose, with evidence. For choices, give **options with reasons and a recommendation**, not just one answer.
2. I decide, or delegate ("your discretion", "you decide", "use your best judgment"). When I delegate, decide, then state what you decided and why in one place.
3. Write a short round doc (`docs/rounds/roundNN_<topic>.md`).
4. Add a row to `docs/decisions_log.md`.
5. Update `docs/design_spec.md`.
6. Then code and tests.

### 2.2 Honesty rules (non-negotiable)
- **Provenance for every fact.** Mark each claim in docs:
  - **(obs.)**: you probed, downloaded or computed it in this project. Record the command or script that produced it.
  - **[verify]**: from memory or a secondary source, not yet checked. Never build code on a [verify] fact without flagging it.
- **Never fabricate a citation, number, URL or quote.** In Claude Science, a fresh-context reviewer caught several fabricated or unsupported citations (an invented author list for a hedge-fund liquidation paper, arXiv IDs claimed as "found by web search" with no search in the log, a made-up search-result label used to rebut the reviewer). If you can't retrieve a source, say so and mark it [verify].
- **When you're wrong, say so plainly and fix it** (as in round 15: "I was wrong to say $1.5M was the lowest step").
- **Never touch the sealed hold-out** (2025-09-22 → 2026-09-21) except through the single logged `final-test` path (§7.2).
- **Report assumptions separately from measurements.** Every analysis ends with "measured" vs "assumed" lists, as in `docs/capital_sizing.md` §9.

### 2.3 Communication style
- Plain English. I'm strong in maths but new to electricity markets, so define terms the first time (I didn't know what `month` and `loc_age_days` meant until asked).
- Show numbers, not just conclusions.
- Short replies between tool calls. Put the detail in the docs.
- If my message has a placeholder or seems cut off, ask rather than guess.
- Ask before anything expensive or hard to undo: large downloads (over about 1 GB), deleting data, changing a decided design point, or anything touching the hold-out.

### 2.4 Check-in points (stop and show me)
- End of M0: `market_rules.md`, `maths.md`, and the explorer working in a browser.
- End of M1.5: I open the app and change a colour and a label myself.
- End of M3: the simulator reproduces `capital_sizing.md`'s numbers.
- End of M4: the planted-signal test.
- End of M7: the first real report card.
- End of M9: the tutorial on a clean machine, offline, plus a bot exported to a single file.
- **Pacing (decided round 23):** work through the milestones in order, committing each round, and stop only at these check-ins. Ask questions in the conversation as they come up.

---

## 3. Where things stand (2026-10-23)

**Design: done.** Design spec v3.1 consolidates rounds 3–16. Settled: market, data sources, the 25 features, bot representation, career model, fitness, MAP-Elites map, report-card gates, bundle layout and milestones.

**Code: one vertical slice.**

| Built | What it is |
|---|---|
| `src/evobots/config/capital.py` | `CapitalSettings` frozen dataclass: defaults, bounds, validation, collateral, ruin floor, per-hub caps, sizing rule, warnings |
| `src/evobots/config/__init__.py` | `load_capital(config_path, overrides)`: code defaults < TOML `[capital]` < command line |
| `src/evobots/sizing.py` | point-in-time trailing p99 daily loss (365 days, newest usable day D−6, 90-day warm-up) |
| `src/evobots/storms.py` | reporting helper: fitness with and without named storm days |
| `src/evobots/cli.py` | `python -m evobots.cli capital [config] [--starting-capital …]`, the only command so far |
| `configs/10_miso_hubs.toml` | the `[capital]` table |
| `tools/build_hub_sample.py`, `tools/fetch_2015_2018.py` | build the Stage A calibration sample from MISO's server |
| `tools/capital_analysis.py` | rebuilds every number in `capital_sizing.md`; includes `explorer_expected()` |
| `tools/capital_explorer.html` | an interactive capital explorer. **Likely broken** (see below). |
| `tests/test_capital.py` (14), `tests/test_sizing.py` (9), `tests/test_floor_caps_storms.py` (17) | 40 tests, all passing in Claude Science |
| `docs/capital_sizing.md` plus CSVs and figures | the full record behind the capital defaults |

**Empty:** `data/`, `features/`, `market/`, `bots/`, `simulate/`, `career/`, `qd/`, `assess/`, `deploy/`, `app/`. No M1 data builder yet. The only data so far is a calibration sample: 8 hubs, 2019-01 → 2025-09, plus a 2015–2018 check and 33 days of cleared bids. It was built inside Claude Science's sandbox and **was not carried over**. Only the summary CSVs exist. You will re-download.

**Status in the repository (round 22, obs.):** the capital slice in the table above is **rebuilt** and passes 133 tests that reproduce `capital_sizing.md` (§4). From Claude Science: `capital_sizing.md`, `decisions_log.md` and seven of its CSVs. Not yet rebuilt: `tools/capital_explorer.html` (replaced by the Capital page at M1.5, §15), `tools/build_hub_sample.py` and `fetch_2015_2018.py` (replaced by `tools/fetch_miso_prices.py` and `build_miso_hub_prices.py`), and the docs listed in `docs/rounds/round21_reconciliation.md` §4. **The full MISO day-ahead and real-time price archive for every location (2005-04-01 → today) has been downloaded and parsed** into a hub table, a location list and a coverage report (§7.0). What exists: this briefing, tooling config, `docs/market_rules.md`, `docs/glossary.md`, the round docs, probe and fetch scripts in `tools/`, and a link-checker test. Every answer about traders, evolution or the app below describes the **design**, not working software.

**Known problems:**
1. *(Fixed round 24: rebuilt as a page of Python-computed values with a browser test.)* `capital_explorer.html` had a JavaScript syntax error: an unescaped apostrophe in "MISO's" inside a single-quoted string, which probably stops the whole script. It was never opened in a browser. Fix it in M0 and add a headless browser test.
2. The original brief asked for **one self-contained file** for the engine and for each bot. The spec describes a project folder. The proposal is in §14.6; it needs my confirmation (§17.1).

---

## 4. Files you should find

I'll put the project files into this layout. **Round 22: build the project independently.** Rebuild anything missing from this briefing and the docs, prove it against the recorded numbers, and ask me questions directly in the conversation instead of waiting for files. If an original file arrives later, compare it with the rebuild and report the differences.

```
evobots/
├── CLAUDE.md                      ← this prompt (optional)
├── pyproject.toml · uv.lock      ← may not exist yet; create in M0 if missing
├── configs/10_miso_hubs.toml
├── src/evobots/
│   ├── __init__.py                 "evobots: evolving MISO virtual-trading bots with quality-diversity search."
│   ├── cli.py · sizing.py · storms.py
│   └── config/  __init__.py · capital.py
├── tests/  test_capital.py · test_sizing.py · test_floor_caps_storms.py
├── tools/  build_hub_sample.py · fetch_2015_2018.py · capital_analysis.py · capital_explorer.html
└── docs/
    ├── design_spec.md              (= design_spec_draft.md, v3.1)
    ├── decisions_log.md
    ├── capital_sizing.md
    ├── bot_inputs_and_representation.md
    ├── decision_questions.md · paper_digest.md · github_comparison.md · inventory.md · iso_comparison.md
    ├── rounds/  round3_market_and_survival.md · round4_electricity_virtual_trading.md · round5_iso_universe_history.md
    │            round6_miso_history_holdout.md · round7_consistency_and_shocks.md · round8_universe_shocks_weather.md
    ├── plans/   project_workflow.md · full_task_list_and_app_plan.md · engineering_standards.md
    └── data/    hub_price_stats.csv · hub_volume_stats.csv · capital_sweep.csv · fixed_cost_capital_floor.csv
                 headroom_trailing.csv · trailing_p99_daily_loss.csv · trailing_breach_rate_by_year_2015_2025.csv
                 minbtl_table.csv · miso_history_options.csv · miso_location_persistence.csv
                 miso_capacity_by_tech_monthly.csv · nws_pfm_coverage_sample.csv · virtual_bidding_literature.csv
                 github_comparison.csv · figures/*.png
```

Notes:
- Some files exist twice in the claude.ai project (uploaded twice). They should be identical. If two copies differ, tell me.
- Claude Science also produced `evobots_stage_a_capital.zip` (118 KB, the code bundle). If I give it to you, compare it with the loose files and report differences.
- The 11 research PDFs are in `C:\Users\areeb\Downloads\Trying to evolve trading bots` on my laptop. They aren't needed for building; `paper_digest.md` summarises them.
- `tests/test_floor_caps_storms.py` reads `docs/hub_volume_stats.csv`. If the test's path differs from the layout above, fix the path, not the data.

**Step zero of M0:** run the 40 tests as they are. They must pass before any rename or refactor. If they don't, report why (likely a path or packaging issue) and fix only that.
**Round 22:** the original code and its 40 tests never arrived. Instead, the capital slice (`config/capital.py`, `config/__init__.py`, `sizing.py`, `storms.py`, `calibration.py`, `cli.py`, `configs/10_miso_hubs.toml`) was rebuilt from `capital_sizing.md`, and 133 tests check it against every recorded number: `hub_price_stats.csv`, `trailing_p99_daily_loss.csv` (2,456 days), `trailing_breach_rate_by_year_2015_2025.csv`, `capital_sweep.csv`, `headroom_trailing.csv`, `fixed_cost_capital_floor.csv`, and the storm-sensitivity values. Setting names follow §14.1 (`daily_risk_budget_fraction`, `credit_share_fraction`, `liquidity_share_fraction`); floors are off by default (§10.1). The tests read a committed daily benchmark series (`docs/data/benchmark_full_size_daily_pnl.csv`), so they run offline.

---

## 5. Environment

### 5.1 My machine
- Windows laptop (paths like `C:\Users\areeb\...`).
- 24 GB RAM, about 12 GB usually free.
- 20 CPU cores.
- NVIDIA RTX 4060 with 8 GB.
- It isn't on 24/7, so long runs must stop and resume cleanly.

You may be running on this machine or in a cloud container. Check which, say so, and don't assume Windows paths exist if you're in Linux.

### 5.2 Stack (decided)
- Python 3.13 with `uv` (repo plus `uv.lock`; internet is fine on first install for packages, never needed for market data).
- NumPy, and Numba for the hot loops (`cache=True`).
- PyArrow or Polars for CSV ingestion, pandas where it is already used, openpyxl and xlrd for EIA spreadsheets, `requests` for downloads.
- matplotlib only in `tools/` analysis scripts.
- Own code for MAP-Elites (about 150 lines) and the GP; no DEAP.
- Optional GPU backend later, behind the same `evaluate_batch()` interface.
- Tests: pytest, pytest-socket (networking blocked), and Playwright (offline browser tests).
- If the app uses UI option A: FastAPI, Jinja2, a vendored Apache ECharts and KaTeX.

### 5.3 Git
Initialise a repo if there isn't one. Commit at the end of every task with a clear message. Never commit downloaded raw data, the built store, the hold-out, or `config/local.toml`; add them to `.gitignore`.

### 5.4 Network access and data-source registration (important)
Claude Science reached each data site only after I approved its domain. Your environment may block domains too. So:
1. **Before downloading anything,** probe every domain in §7.9 with one small, polite request (HEAD, or a small known file). Report a table: domain, reachable or blocked, HTTP status.
2. **If a domain is blocked,** don't retry with other tools or proxies. Give me the exact list of domains to allow and why each is needed. While waiting, carry on with whatever doesn't need it.
3. **If a source wants registration, an API key or an email address** (for example a sign-up form, or a "please put a contact email in your User-Agent" rule), stop and ask me. Don't register on my behalf. All sources chosen so far are keyless, so this should be rare; the design depends on keyless sources (PJM and ERCOT were excluded because they need keys).
4. **Contact email for polite bulk downloading:** identify yourself to the servers, since the forecast fetch alone is roughly 70,000 requests to the Iowa Environmental Mesonet. Check each site's usage notes for its own rules (read in round 24: `docs/data_sources.md` §2; MISO's terms forbid automated access, §5 there). Send a descriptive User-Agent, e.g. `evobots/0.1 (research; contact: <CONTACT_EMAIL>)`. Store the email in `config/local.toml` (git-ignored), never in code or docs. If `<CONTACT_EMAIL>` hasn't been filled in, ask me for it before the first bulk download.
5. **Be polite to servers:**
   - at most 4 parallel downloads per host;
   - about 0.5 s between requests for IEM;
   - retry 3 times with backoff;
   - treat 404 as "file doesn't exist", not as an error;
   - write-then-rename for every downloaded or parsed part, so a crashed run resumes (the existing `build_hub_sample.py` already does this);
   - record every file's URL, SHA-256 and download date in `data/manifest.toml`.

---

## 6. The market: what a bot trades

### 6.1 Mechanics
- On day **D−1**, MISO runs the **day-ahead (DA)** market for each hour of day D and publishes an hourly price at every location: the **LMP** (locational marginal price), in $/MWh, with energy, congestion (MCC) and loss (MLC) components.
- On day **D**, the **real-time (RT)** market re-prices against actual conditions.
- A virtual trader takes a DA position that is automatically reversed in RT:

| Position | Also called | Clears when | Profit per MWh |
|---|---|---|---|
| DEC | virtual demand bid | bid price ≥ DA LMP | RT − DA |
| INC | virtual supply offer | offer price ≤ DA LMP | DA − RT |

For one bid at location n, hour h, with q MW and limit price b:
```
cleared   = (DA[n,h] <= b) if DEC else (DA[n,h] >= b)
direction = +1 if DEC else -1
pnl       = cleared * q * direction * (RT[n,h] - DA[n,h]) - fees(q, cleared)
```

### 6.2 Facts measured in Claude Science (obs.)
- **Clearing is all-or-nothing.** On 33 days of MISO's cleared-bids report (2023-01 → 2025-09), the price rule predicts cleared status for **99.5 %** of single-block virtual bid-hours market-wide (95 % CI 99.4–99.6 %) and **100.0 %** at hubs. Partial fills are about 0.16 %.
- **Other traders' clearing rates:** 48.8 % [46.1, 51.4] of bid-hours market-wide, **72.1 % [70.7, 73.5]** at hubs. A bot's own clearing rate is an **output** of its limit prices, never a parameter.
- **Volume:** a median hour clears about 11,800 MW of DEC and 11,600 MW of INC across all locations. A single participant at a hub-hour clears a median of 8 MW. MISO's minimum bid is 0.1 MW.
- **Cleared-bids report:** `YYYYMMDD_bids_cb.zip`, exists from 2023. Columns include `Type of Bid` (D = DEC, I = INC), `MW` (the cleared amount; 0 = not cleared), `MW1..MW9` / `PRICE1..PRICE9` (the bid curve), `LMP`, `Region` and an anonymous `Market Participant Code`. It has no location field. Its LMP is the DA **ex-ante** price (`YYYYMMDD_da_exante_lmp.csv`). About 7.9M rows on the sample days are placeholder rows with no curve and 0 MW; exclude them.
- **Price-taker assumption:** our bids don't move prices. This is enforced by a cap per location-hour and stated in every report.
- **Costs (researched in round 18; `docs/market_rules.md` §3):** a per-MWh administration fee on cleared virtuals (Schedules 17 and 24), plus the **Revenue Sufficiency Guarantee (RSG)** uplift allocation. Double them in stress tests.
  - **Measured from MISO's documents:** which charges apply, and how they net (admin fees and day-ahead RSG on the net position per node-hour; real-time RSG on net virtual supply summed over all nodes per hour); RSG on virtual supply had three eras (none before 2008-11; high 2008-11 → 2011-03; much lower from 2011-04).
  - **Estimated:** the rates themselves (build with labelled placeholder rates until the file arrives; decided round 20). Schedule 17 + 24 ≈ $0.090/MWh in October 2026 is from search-index quotes [verify]; the RSG rate history is missing until MISO's Rates Factors file is in `data/inbox/`.
  - **Costs vary with time.** `fees.py` reads a cost table by month (hour for RSG) and era, never one constant. Every rate is labelled "measured" or "estimate" in every report.

### 6.3 Credit and eligibility (checked in documents, round 16)
- **Collateral** (MISO Tariff Attachment L, section IV): `collateral = daily Virtual MWh Limit × MPD × VMEW`, where VMEW = 2 days.
  - MPD is the greater of the 50th-percentile DA−RT differential over the previous 12 months (reset each May) and **$12/MWh** (the floor, checked).
  - Use MISO's published MPD [verify at M0].
- At full Stage A size (936 MWh/day), collateral is only **$22,464**, while the worst day lost $492k. So the simulator must **mark equity daily**, not only collateral.
- **Eligibility:** Attachment L **v56.0.0, effective 2024-06-03, §III.B** ("Demonstration of Appropriate Person Status"): net worth > $1M **or** total assets > $5M. This is **one of seven routes** listed in MISO's *Minimum Participation Requirements* (energy business, governmental entity, financial statements, cash deposit > $5M, corporate guaranty, irrevocable letter of credit, other). It is not a hard requirement for every trader. Minimum capitalization is a separate test in §III.C. Version 57.0.0 (filed 2025-07-14 in docket ER25-2845, effective 2025-07-15) has the same virtual-trading text (obs., round 18). No later version was found by search (round 27).
- Real trading needs MISO market-participant registration and collateral. **Out of scope.**

### 6.4 Information timeline (no look-ahead)

| Time (Eastern) | Event |
|---|---|
| D−1, bid deadline: **10:30 EPT since 2016-11-05; 11:00 EST (noon clock time in summer) before** (round 18) | DA bids for D close. **The bot decides at 10:30 EPT on D−1 for every year** (decided round 20; never later than the real deadline) |
| D−1, 13:30 EPT since 2016 (15:00 EST before) | DA prices for D published |
| D | RT prices for D produced |
| about D+5 (obs.: on 2026-09-26 the newest *final* RT file was 2026-09-21) | final RT prices for D published |

- Every data column carries an `available_at` timestamp. One function, `visible(column, decision_time)`, is the **only** way features read data.
- With the 5-day lag, on decision day D−1 the newest operating day with known P&L is **D−6** (already encoded in `sizing.py`).
- *Preliminary* RT prices are **not archived**: only the last ~3 days exist on the server (obs., round 18, `tools/probe_rt_archive.py`). The lag stays.
- **Look-ahead test:** change all data on or after a decision time; no feature at that decision time may change.

**What a bot sees at each decision (round 19):**
- **Past electricity prices: yes.** DA prices up to and including day D−1's (published the afternoon before the decision) and final RT prices up to D−6, through features 1–7 (§8).
- **Futures quotes and past futures prices: no.** EIA's free gas futures stop on 2024-04-05; MISO power futures history is not free (searched in round 27: CME's pages show only current settlements and ICE publishes contract specifications; no free history found); and §7.1 requires every input for 2005–2026 from one keyless source. They stay out (decided round 20, R19-5) unless I supply such a source.
- **Outside factors:** gas (Henry Hub spot), policy uncertainty (EPU), weather forecasts, wind and solar capacity, calendar (§8). GPR, oil and the World Bank series are reporting only.
- **Proof for the user:** the Trader page has a **"What did it see?"** panel: pick any day and it shows the exact input values the trader saw at 10:30 EPT on D−1 and the bids it made.

### 6.5 Access risk
MISO announced that its public pricing reports would stop updating from 12 December 2025, in favour of its account-based Data Exchange. Its July 2026 page said they stay available while a new timeline is reviewed, and files were still updating on 2026-09-24 (obs.). Consequences:
- bundling a data snapshot is essential;
- paper-live mode may lose its feed;
- the later CAISO adapter is the fallback.

---

## 7. Data

### 7.0 Import status (round 20)

| Data | In the repository (obs.) | Known gaps and quirks |
|---|---|---|
| MISO DA / RT LMP, **every location** | **downloaded 2026-10-24**: 3,208 files, 5.3 GB raw (`tools/fetch_miso_prices.py`); DA for 7,512 days and RT for 7,507 days outside the hold-out; hold-out files stored apart in `data/holdout/raw/` and never opened | MISO's market opened 2005-04-01; nothing older exists (2005-03 is a 404), so the history is ~21.5 years, not 25. Only missing: final RT for the newest ~5 days (not yet published). See `docs/data_coverage.md` |
| Parsed store (git-ignored) | `data/store/hub_prices.csv.gz` (day × hour × hub: DA/RT LMP, MCC, MLC), `locations.csv` (5,519 locations with first/last day), `daily_coverage.csv` (`tools/build_miso_hub_prices.py`) | the all-location memory-mapped store (§7.11) is still to build (M1/M8) |
| Provenance | `data/manifest.toml`: URL, SHA-256, size, date for every file (committed) | |
| MISO preliminary RT | last ~3 days only | not archived |
| MISO cleared bids | **2023-01-01 → 2026-01-23** (1,119 days, with DA ex-ante prices; round 23). The fetch was stopped in round 25 because MISO's terms forbid automated access | published about **90 days late** (obs.: newest 2026-07-25 on 2026-10-24); needed for O9 and the liquidity medians |
| NWS forecasts | **fetching** (round 23): 9 offices × 7,878 decision days, ~8 h at the polite rate | parser at M1 |
| Henry Hub, EPU, GPR, EIA-860M | not downloaded yet | M1 |

**Check against Claude Science (obs., round 21, `tools/check_against_claude_science.py` → `docs/data/claude_science_check.csv`):** from the downloaded archive, for 2019-01-01 → 2025-09-21:
- **all 176 values** of `docs/data/hub_price_stats.csv` agree to rounding. Correction (round 28): in round 21 the eight excess-kurtosis values agreed only within a 0.05 % tolerance; Claude Science used the bias-corrected sample estimate (pandas' `kurt`), and with it all 176 agree at the recorded precision (`evobots data build --stage A`);
- the 12 full-size benchmark numbers of `capital_sizing.md` §4 agree to the dollar (e.g. always-INC 1-in-100-day loss $27,897, worst day $492,173 on 2022-12-23; always-DEC worst day $176,554 on 2021-02-18);
- the point-in-time trailing p99 of §4b agrees exactly: the eight table rows, the range $10,432–$44,843, median $24,155, the 2019-04-06 end of warm-up, and the **2.16 %** breach rate with every yearly value.
- So the archive is the same data as the calibration sample, and `sizing.py`'s rules are pinned down independently. §4b's lost figure is redrawn as `docs/data/figures/point_in_time_full_size_threshold.svg`.

Gaps are never filled silently: a missing day is missing.

### 7.1 Principles
- **Consistent:** every input must exist for the whole 2005–2026 span and come from one source and procedure. Inputs that start late (MISO load forecasts, 2015+) or stop (EIA gas futures, 2024-04) are excluded from bot inputs.
- **Point-in-time:** only what a trader could see before the DA deadline.
- **Offline once built.** The bundle runs with no internet; downloading is a separate, explicit step.
- **Huge data handled explicitly:** columnar, memory-mapped, one file per year, streamed, never loaded whole.

### 7.2 Periods (decided)

| Use | Period |
|---|---|
| Evolution and walk-forward validation | **2005-04-01 → 2025-09-21** (about 20.5 years; MISO's market opened April 2005) |
| **Sealed hold-out** | **2025-09-22 → 2026-09-21** (12 months, covering every season once) |
| Forward / paper-live | 2026-09-22 onward |

Hold-out rules:
- It is stored as a separate file in `data/holdout/`, which evolution code can't open.
- It is opened only by `evobots final-test`, scored **once per finished run**, and every opening is logged (who, when, which run).
- The 2026 Iran war (from 2026-02-28) falls inside it, so it is a hard, realistic test.

### 7.3 MISO prices (core input)
Server: `https://docs.misoenergy.org/marketreports/` (keyless). Three file eras (obs.):

| Years | Day-ahead | Real-time | Notes |
|---|---|---|---|
| 2005-04 → 2015-02 | `{YYYYMM}_da_lmp_csv.zip` (monthly, one CSV per day inside) | `{YYYYMM}_rt_lmp_final_csv.zip` | 2005 files have **no `Value` column** (one LMP row per node) and **space-padded names**. From at least 2010, rows carry LMP, MCC and MLC. |
| 2015-02-19 → 2022-12 | `{YYYYMM}_da_expost_lmp_csv.zip` | `{YYYYMM}_rt_lmp_final_csv.zip` | 2015-02 is split: the old-style zip exists, and the new-style zip holds only 2015-02-19 onward. |
| 2023-01 → today | daily `{YYYYMMDD}_da_expost_lmp.csv` | daily `{YYYYMMDD}_rt_lmp_final.csv` | |

- **CSV layout (2015+):** a few preamble lines, then a header starting `Node,Type,Value,HE 1,…,HE 24`, then one row per node and value type. Keep `Value == "LMP"` (and MCC/MLC when building components). Strip names. The header must be **found by searching for the line starting `Node,`**, not assumed at a fixed row. `tools/build_hub_sample.py: parse_lmp_csv()` is the working reference.
- **Also on the server:**
  - `{YYYYMMDD}_da_exante_lmp.csv` (used to attribute cleared bids);
  - `{YYYYMMDD}_bids_cb.zip` (cleared bids, 2023+);
  - `{YYYYMM}_df_al_xls.zip` (load forecast, 2015-01+, **excluded** from bot inputs);
  - DA/RT binding-constraint files;
  - 5-minute RT as weekly zips.
- **Size:** monthly zips are about 1.5–7.7 MB each; the whole 2005–2026 archive is about **3.3 GB zipped** (estimate).
- **Location counts (obs., six snapshot days):** 2005-04-01: 1,471; 2010-06-01: 1,939; 2013-12-31: 2,174; 2015-01-01: 2,231; 2022-12-31: 2,375; 2026-09-24: 2,628.
  - 4,618 distinct names across those six days; about 2,136 priced per day on average.
  - 2024-01-15 breakdown: 1,539 generator nodes, 425 load zones, 405 "hub"-type aggregates (only **8 are trading hubs**), 45 interfaces.
  - 387 locations persist under the same name in all six snapshots (266 generators, 81 load zones, 37 interfaces, 3 hubs).
- **Trading hubs, first and last day with DA prices (obs., full archive, round 20; `docs/data_coverage.md`):**
  - CINERGY 2005-04-01 → 2011-12-31; ILLINOIS, MICHIGAN, MINN 2005-04-01 → today;
  - FE 2005-09-01 → 2011-05-31;
  - INDIANA 2011-03-01 → today. **It is not a rename of CINERGY:** over the 7,344 overlapping hours their prices differ (DA median |difference| $0.23/MWh, maximum $17.74; identical in only 57 hours), so they are different node sets and are treated as different hubs;
  - ARKANSAS, LOUISIANA, TEXAS from **2013-12-19** (MISO South integration);
  - MS 2017-12-01 → today, giving 8 hubs.
- **Hours** are hour-ending **Eastern Standard Time all year**, as every file states, so every day has 24 hours and no daylight-saving shift (obs.).
- **Congestion and loss components** (MCC, MLC) exist from **2005-06-16** in both markets (obs.); before that, LMP only.
- **Day-ahead file choice (round 26, obs.):** MISO's Extended LMP went live on **2015-03-01** (Wang et al., MISO, FERC technical conference, June 2015), and the ex-post DA files belong to it. Before that day there was one DA price, in the `da_lmp` files, so they are used. The one earlier ex-post file (2015-02-19) is wrong for that day: hub averages $29–33 against real-time $71–117 and `da_lmp` $52–103. From 2015-03-01 the ex-post file is used, because virtuals settle at the DA ex-post LMP (`market_rules.md` §1).
- **Calibration sample facts (obs.):**
  - 2019-01-01 → 2025-09-21: 58,944 hours per hub, no gaps.
  - 2015-03 → 2018-12: seven hubs complete; MS from 2017-12.

### 7.4 Weather forecasts: NWS Point Forecast Matrices (bot input)
- **Source:** the National Weather Service's own forecasts, archived by Iowa State's **Iowa Environmental Mesonet (IEM)**. Keyless.
  - URL: `https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?pil=PFM{WFO}&sdate=YYYY-MM-DD&edate=YYYY-MM-DD&fmt=text&limit=N`
- **What it holds:** several issues a day. Each is a table of 3-hourly temperature, dew point, humidity, wind, cloud cover and precipitation chance for named towns, about 7 days ahead, with the issue time.
- **Offices (9):** MPX (Minneapolis), LOT (Chicago), ILX (central Illinois), IND (Indianapolis), DTX (Detroit), LZK (Little Rock), JAN (Jackson MS), LCH (Lake Charles), LIX (New Orleans).
- **Coverage (obs., 15 July of 2005/2008/2012/2016/2020/2024):** every office had ≥ 2 issues each sampled day (`nws_pfm_coverage_sample.csv`). 2026-09-24 also returns a product.
  - Example: the 2005-04-01 3 PM Minneapolis issue gives min/max 27/56 °F for 2 April.
- **Parser traps:**
  - the text switched from ALL CAPS to mixed case between 2016 and 2020, so search case-insensitively (counting "point forecast matrices" needed `.lower()`);
  - read column positions from the header lines, never fixed offsets.
- **Use:** the latest issue before the DA deadline.
- **Size:** about 1.4 GB raw to fetch (one issue per office per day, about 20 KB each); the parsed table is about 16 MB.
- **Plan:** fetch once, parse, and **bundle the parsed table** plus the script.
- **Hub → office link (decided round 23, nearest-load rule):** MINN→MPX, MICHIGAN→DTX, INDIANA→IND, **ILLINOIS→ILX** (MISO's Illinois is Ameren's central and southern Illinois; Chicago is PJM), ARKANSAS→LZK, MS→JAN, **LOUISIANA→LIX**, **TEXAS→LCH**. LOT is fetched but feeds no hub. **Town (decided round 28):** each hub uses one fixed load-centre town of its office: Minneapolis, Detroit, Indianapolis, Peoria, Little Rock, Jackson, New Orleans, Beaumont (`src/evobots/data/regions.py`); a missing town means missing inputs that day.
- **Fetch (round 23):** `tools/fetch_nws_forecasts.py`, one request per office per decision day for the newest issue in the 24 hours before 10:30 EPT on D−1; hold-out days go to `data/holdout/raw/nws/`.
- **Set aside:**
  - GFS MOS machine forecasts (IEM `cgi-bin/request/mos.py`) only start 2007-05-03;
  - IEM **ASOS** airport observations (`cgi-bin/request/daily.py`, covers 2005) are for **reporting only**, to measure forecast skill. Bots never see same-day actuals.

### 7.5 US natural gas: EIA Henry Hub spot (bot input)
- **URL:** `https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDd.xls`. Keyless; read with `sheet_name="Data 1"` (or index 1), `skiprows=2`.
- **Coverage (obs.):** daily, 1997-01 → 2026-09-22, trading days only. Lag 1 trading day (`src/evobots/data/visible.py`).
- **Observed:** US gas peaked at **$30.72/MMBtu on 2026-01-23**, before the Iran war (cause not checked). In March 2026 Henry Hub **fell 16 %** (Feb mean $3.62 → Mar mean $3.04) while WTI rose 42 %.
- **Not used as inputs:**
  - EIA gas futures `RNGC1d.xls` stop 2024-04-05;
  - WTI spot `https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls` is reporting only (MISO burns almost no oil, and oil and US gas moved in opposite directions in 2026).

### 7.6 Policy uncertainty: EPU (bot input)
- **Source:** Baker, Bloom & Davis US Economic Policy Uncertainty, daily, newspaper-based. Keyless.
  - URL: `https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv`, with columns (obs.) `day, month, year, daily_policy_index`.
- **Coverage (obs.):** 1985 → 2026-09-25. Posted the day after; usable at the decision two days after the observation, since the posting time of day is unrecorded (D-92, round 28).
- **Why it's kept** (my decision, round 11): it is the only input that flagged COVID (EPU's mean over 2020-03-09 → 04-30 was 513, 3.5× the highest 53-day mean of 2015–19 (145) and above every single 2015–19 day except 2016-06-25 (587, the day after the Brexit vote); obs., round 28, `tests/test_series.py`; the round-11 wording "above every baseline day" was not exact).

### 7.7 Geopolitical risk: GPR (reporting only)
- **Source:** Caldara & Iacoviello (Federal Reserve Board), daily.
  - URL: `https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls`
- **Columns (obs.):** `DAY`, `date`, `GPRD` (headline), `GPRD_THREAT` (categories 1–5), `GPRD_ACT` (6–8), `GPRD_MA7`, `GPRD_MA30`, `N10D` ("Number of articles (10 recent newspapers, 1985-)", the file's own label; obs. round 27), `event`, `var_name`.
- **Scaling:** 100 = the 1985–2019 average. Coverage 1985 → 2026-09-21 (obs.).
- **Iran war (obs.):** threats peaked at 299 on Feb 24; GPR 274 on Mar 1 and 501 on Mar 2 (threats 602, acts 553). Mean GPR over 2026-02-28 → 03-31 was 319. Russia–Ukraine (2022-02-24 → 03-31) was 318. GPR did **not** flag COVID (29th percentile).
- **Why it's not a bot input** (round 10, my point): most geopolitical threats don't touch MISO's fuel; only energy-related shocks matter. GPR was replaced by `gas_vol_20d` and kept for event analysis in reports.
- **Revisions (obs., round 27):**
  - **GPR:** "The latest data are preliminary and subject to revisions", but the site archives every daily vintage (`data_gpr_daily_recent_YYYYMMDD.xls`), so past versions are recoverable.
  - **EPU:** "each day we update the data from the previous 30 days … so these data are subject to changes", and no vintages are archived. The downloaded history therefore holds revised values, a small look-ahead risk for `epu`, which the hindsight check (§8) covers.
  - Paper-live mode archives each day's copy of both from now on.

### 7.8 Generator fleet: EIA-860M (bot input via two capacity features)
- **URLs:**
  - latest: `https://www.eia.gov/electricity/data/eia860m/xls/{month}_generator{year}.xlsx` (e.g. `august_generator2026.xlsx`; the builder must find the newest available month);
  - archive: `https://www.eia.gov/electricity/data/eia860m/archive/xls/`
- **Sheets:**
  - `Operating`, `Retired`, `Planned`;
  - the header row is found by searching for "Plant ID" (around row 2);
  - fields include `Balancing Authority Code`, `Technology`, capacity MW, latitude/longitude, operating month/year, retirement month/year.
- **Rebuild:** MW operating per region per month, from operating and retirement dates.
  - Filter `Balancing Authority Code == "MISO"` (today's code).
  - Count a plant only from the date its area joined MISO (MISO South: December 2013).
  - Assign each plant to the hub whose forecast town (§7.4) is nearest by great-circle distance (decided round 28; Iowa splits near Des Moines).
  - Technology groups: Wind, Solar, Battery, Coal, Natural Gas, Nuclear, Other.
- **Observed MISO fleet (GW):**

| | 2005-04 | 2015-01 | 2026-08 |
|---|---|---|---|
| Coal | 71.1 | 73.8 | 47.5 |
| Gas | 79.3 | 83.9 | 83.8 |
| Wind | 1.3 | 14.3 | 33.7 |
| Solar | 0.0 | 0.1 | 24.4 |
| Battery | 0.0 | 0.0 | 1.2 |

  Full table: `docs/data/miso_capacity_by_tech_monthly.csv`.
- **Planned projects:** only monthly snapshots from January 2016 (the January 2013–2015 files aren't on EIA's server), so they are **reporting only**.
- **Transmission:** no free, consistent dataset found; its effect shows up in the congestion features.
- **Corrections (obs., round 27, EIA-860M page):** "Estimates will be corrected without specific acknowledgment or explanation in subsequent month's inventory." Monthly files are archived from January 2015, so M1 measures the size of the corrections by comparing them.

### 7.9 Complete source list and the domains to allow

| Domain | Used for | Role |
|---|---|---|
| `docs.misoenergy.org` | DA/RT LMP all eras; ex-ante LMP; cleared bids; (load forecast, constraints) | **core input** |
| `cdn.misoenergy.org` | MISO documents: Attachment L (credit policy), Minimum Participation Requirements, *Virtual Trading in MISO*, Market Reports Directory (.xlsx), Business Practices Manuals, tariff, fee and RSG rate pages | rules (M0) |
| `www.misoenergy.org`, `help.misoenergy.org` | market-report archive pages, Data Exchange FAQ | rules and access risk |
| `mesonet.agron.iastate.edu` | NWS PFM forecasts; ASOS observations | input; reporting |
| `www.eia.gov` | Henry Hub spot; WTI spot; EIA-860M; EIA-860 annual | input; reporting |
| `api.eia.gov` | EIA bulk files (`/bulk/NG.zip`, `/bulk/PET.zip`), only if needed | optional |
| `www.policyuncertainty.com` | EPU daily | input |
| `www.matteoiacoviello.com` | GPR daily | reporting |
| `thedocs.worldbank.org` | World Bank "Pink Sheet" monthly prices: `…/CMO-Historical-Data-Monthly.xlsx`, sheet `Monthly Prices` | reporting |
| `oasis.caiso.com` | CAISO adapter (later): `oasisapi/SingleZip?queryname=PRC_LMP&market_run_id=DAM&…&node=TH_NP15_GEN-APND&resultformat=6`; rolling ~3-year window; pace about 1 request per 5–6 s | later |
| `www.ams.org` | Bailey et al. 2014, *Pseudo-Mathematics and Financial Charlatanism* (`/notices/201405/rnoti-p458.pdf`); returned HTTP 403 in Claude Science, so the MinBTL numbers are a reimplementation not checked against the paper's worked examples | verification |
| `arxiv.org`, `export.arxiv.org` | the 8 virtual-bidding papers (§12.3) | verification |
| `pypi.org`, `files.pythonhosted.org`, `github.com` | packages | install |
| `api.crossref.org`, `api.semanticscholar.org`, `export.arxiv.org` | checking references and fetching abstracts (`tools/check_references.py`) | verification |

Explored in Claude Science and then **dropped** (don't download): `data.binance.vision` (crypto), EIA futures series RCLC1–4 and RNGC1 (stop 2024-04-05), `www.cftc.gov` Commitments of Traders, Fed H.10/H.15, `mis.nyiso.com` (timed out; NYISO is a possible later generality check).

**"Political stability" and "sun" inputs, as actually designed:**
- Political and news shocks reach bots only as **EPU** (input) and **GPR** (reporting), both mechanical newspaper-count indices.
- Solar reaches bots as **`solar_cap_region`** (EIA-860M) and **`cloud_fcst`** (NWS).
- No irradiance dataset and no country political-stability dataset (e.g. World Bank governance indicators) was adopted. Propose one only if it meets §7.1.

**Why no AI reading of news articles** (round 9):
1. **Hindsight leak:** any modern language model already knows how the 2005–2026 events turned out.
2. There is no free, consistent 2005–2026 news archive.
3. A virtual bid earns RT − DA, so news that moves both prices cancels out. What matters is the DA-vs-RT surprise (weather error, outages, fuel volatility), which the features cover.

### 7.10 Location universe (decided)
- **Whatever locations exist on each day.** A virtual bid lasts one day, so a location appearing or disappearing never strands a position.
- **Bots choose locations by properties, never by name** (type, region, spread volatility, congestion share, etc.), so a bot evolved in 2010 can act on 2026's locations.
- **Staged plan, option E:**
  - **A:** the trading hubs that exist each day (4 in 2005, rising to 8);
  - **D:** clustered representatives, recomputed every rolling year (correlation clustering as in arXiv 2210.06543);
  - **C:** every location.
- `locations.csv` holds name, type, first day and last day.

### 7.11 Storage

| Store | Layout | Size (est.) |
|---|---|---|
| Hub prices | one table, day × hour × hub, 2005–2026 | ≈ 12 MB, **bundled** |
| All-location prices | `prices/{year}.npy` float32 memory-mapped arrays [day, hour, location_index, field], plus `prices/{year}_locations.npy` → `locations.csv` | ≈ 3.2 GB LMP only, ≈ 9.7 GB with components; **built on demand** |
| Global features | day × feature | < 1 MB |
| Regional features | day × region (8 hub areas) × feature | ≈ 2 MB; parsed forecasts ≈ 16 MB, **bundled** |
| Location features | per-year float16 memory-mapped arrays | ≈ 21 MB for hubs; ≈ 5.6 GB for all locations |
| Manifest | `data/manifest.toml`: every source URL, era adapter, SHA-256, download date | – |

- **Bundle:** hub prices 2005–2026, the parsed forecasts, the Henry Hub/EPU/GPR series, the capacity table, the sealed hold-out file, and the manifest.
- **Built by one command:** `evobots data build --stage C --download`. It is resumable, checksum-verified, and offline by default. Without `--download`, it builds from files in `data/bundled/` or `data/inbox/`.
- **Redistribution terms** of each bundled source (MISO, NWS/IEM, EIA, EPU, GPR, World Bank) must be checked and recorded in `docs/data_sources.md` before bundling (M0).

---

## 8. Bot inputs: the 25 features (final, round 12)

**Rules:**
- **Raw units**, each feature tagged with its unit (my decision). Formulas are unit-typed.
- **Point-in-time**, through `visible()` only.
- **Missing** makes any comparison false, so the bot doesn't trade on that input that day.
- **Constants** are drawn from each feature's historical range.
- Known trade-off: $30/MWh in 2005 isn't $30/MWh in 2025. The report shows whether a bot relies on level thresholds.
- **Populated status (round 19):** none of the 25 features has data in the repository yet. The catalogue gets a "populated" field that the build fills in (first day, last day, share of missing days), shown on the Data page.

| # | Code name | Level | Unit | Meaning |
|---|---|---|---|---|
| 1 | `spread_mean_7d` | loc × hour | $/MWh | mean (DA − RT) over the last 7 visible days |
| 2 | `spread_mean_28d` | loc × hour | $/MWh | same over 28 days |
| 3 | `spread_std_28d` | loc × hour | $/MWh | std of the spread, 28 days |
| 4 | `spread_pos_frac_28d` | loc × hour | fraction | share of days with DA > RT |
| 5 | `spread_spike_frac_28d` | loc × hour | fraction | share of days with \|spread\| > $50/MWh |
| 6 | `da_last` | loc × hour | $/MWh | latest DA price for this hour visible at the deadline |
| 7 | `congestion_share_28d` | loc × hour | fraction | congestion component ÷ LMP, 28-day mean |
| 8 | `loc_type` | location | category | hub / load zone / generator / interface |
| 9 | `loc_region` | location | category | the hub whose DA price this location correlated with most over the past 365 days (missing if < 90 days of history) |
| 10 | `temp_max_fcst` | region | °F | NWS forecast high for D (latest issue before the deadline) |
| 11 | `temp_min_fcst` | region | °F | forecast low for D |
| 12 | `temp_fcst_change` | region | °F | today's forecast high minus yesterday's for the same target day D (align by target date, not issue date) |
| 13 | `hdd_fcst` | region | °F·day | heating degree-days from the forecast (base 65 °F) |
| 14 | `cdd_fcst` | region | °F·day | cooling degree-days from the forecast |
| 15 | `wind_fcst` | region | mph | forecast mean wind speed for D |
| 16 | `cloud_fcst` | region | fraction | forecast cloud cover for D |
| 17 | `wind_cap_region` | region | MW | wind capacity operating on D−1 (EIA-860M), replacing `month` |
| 18 | `solar_cap_region` | region | MW | solar capacity operating on D−1, replacing `loc_age_days` |
| 19 | `gas_price` | global | $/MMBtu | Henry Hub, last visible trading day |
| 20 | `gas_chg_5d` | global | $/MMBtu | change over 5 trading days |
| 21 | `gas_vol_20d` | global | %/day | realised volatility of daily log changes over 20 trading days, replacing `gpr` |
| 22 | `epu` | global | index points | US policy uncertainty, lagged 1 day |
| 23 | `hour` | calendar | hour | hour ending 1–24 |
| 24 | `weekday` | calendar | category | Mon–Sun |
| 25 | `holiday` | calendar | boolean | one of the six NERC off-peak holidays; a Sunday holiday also flags the following Monday (round 20; `market_rules.md` §6) |

- **Three tables at three granularities** (global, regional, location), broadcast onto location-hours at evaluation time. Storing everything per location-hour would be about 64 GB.
- **Catalogue:** `features/catalogue.py` holds the registry: code name, **display name** (e.g. `spread_mean_7d` → "Average DA − RT spread, last 7 days ($/MWh)"), unit, one-line meaning, compute function and required columns. The GP unit checker, the hindsight check, the UI labels and the docs all read from it.
- **Example interaction a bot can form:** `wind_fcst × wind_cap_region`, a rough "expected wind output". The same forecast means about 26× more wind MW in 2026 than in 2005.
- **Hindsight check:** every finished bot is re-scored with `epu` and the `gas_*` features set to missing. A bot whose edge depends on them only in early years is flagged "hindsight-suspect".

---

## 9. The bot (the trader)

"Bot" and "trader" mean the same thing; the app says **trader**.

### 9.1 The trader as an organism (round 19)
A trader has three parts:

| Part | What it is | Where you see it |
|---|---|---|
| **Genome** | its slot trees (§9.2–9.3) and numeric genes, as canonical JSON; this is what evolution changes | Trader page → "Tree" |
| **Source code** | a standalone, standard-library Python module `trader_<trader id>.py`, **generated from the genome when the trader is born**. It is the literal executable code: `python trader_R12-184213.py --inputs day.csv` prints that day's bids | Trader page → **View code** (syntax-highlighted, Download) |
| **Life** | its account, bids, equity curve, offspring, and death cause and date if it died | Trader page → "Life" |

- **Code and engine agree exactly.** The fast engine (NumPy/Numba) is an optimisation; the generated file is the reference. An equivalence test on many random days checks they give identical bids. This test moves from M9 to **M4**; the generator in M4 is the same one `export-bot` uses (§14.6).
- **Why evolution edits the tree and not the text:** a random edit to Python text almost never gives a program that runs. Editing typed syntax trees guarantees every child is a valid, well-typed program (strongly typed GP: Montana 1995, *Evolutionary Computation* 3(2), doi 10.1162/evco.1995.3.2.199). The code is printed from the tree, so the two are always the same organism.
- The generated file starts with a header: id, name, parents, the operator that created it, birth evaluation and run, the input list with units, and a plain-English reading of each slot.
- **Code ⇄ genome round trip (round 20):** the generated dialect parses back into a genome. I can edit a trader's file, or write one; if it passes the grammar and unit checks it joins a Refine run as a founder labelled `founder:human`.
- **The trader language** is one typed grammar file, `bots/grammar.py`, shown on its own Docs page. Typed GP (Montana 1995) and grammar-guided GP search the same way here; the grammar form doubles as documentation (`docs/design_rationale.md` A1).
- **Rejected representations,** with reasons in `docs/design_rationale.md` A1: self-replicating machine code (Tierra, Avida), linear and Cartesian GP, PushGP, neural networks, and **language-model mutation** of source code (ELM, FunSearch), which has the same hindsight leak as news-reading (round 9) and breaks offline running and byte-identical resume.

Example of the generated form (illustrative, not a real trader):
```python
"""Trader R12-184213 "amber-heron". Generated by evobots 0.1 from genome 7c2e9a41d0….
Parents: R12-179022 (subtree mutation of `score`). Born at evaluation 18,402 of run R12.
"""
def decide(row):
    """Return (side, limit_price_usd_per_mwh, size_mw) for one location-hour, or None."""
    is_where = row.loc_type in {"Hub", "Loadzone"} and row.spread_std_28d > 18.0
    is_when = 14 <= row.hour <= 19 and not row.holiday
    if not (is_where and is_when):
        return None
    score = row.spread_mean_28d - 0.4 * row.cdd_fcst
    ...
```

### 9.2 Skeleton (every bot has exactly these slots)
```
Bot "7c2e"
  where : loc_type in {Hub, Loadzone} and spread_std_28d > 18.0 $/MWh     boolean formula
  when  : hour in 14..19 and not holiday                                  boolean formula
  score : spread_mean_28d - 0.4 $/MWh/°F·day * cdd_fcst                   number formula ($/MWh)
  side  : DEC if score > +4.0, INC if score < -4.0, else no bid           evolved thresholds
  price : limit = da_last ± 15 $/MWh                                      evolved offset
  size  : 2 MW × min(1, |score| / 10)                                     evolved scale, ≤ cap
  risk  : ≤ 50 MW/day total; pause 5 days after a 3 % daily loss          evolved within hard caps
```
- A positive `score` means the bot thinks RT will exceed DA.
- Every bot prints exactly like this, in two modes (display names by default, code names optionally), and saves as JSON. JSON must round-trip exactly.
- **No learning inside a bot.** It adapts only through its trailing inputs. Evolution does the learning.

### 9.3 Formulas
- **Strongly typed GP trees of at most about 15 nodes per slot.**
- **Primitives:**
  - feature names and constants;
  - `+ − ×`, protected `÷` (÷0 → 0), `min`, `max`, `abs`;
  - `> <`, `and or not`, `in {…}` (categories appear only inside `in`);
  - `if … then … else`.
- **Unit checking:** `+ − > <` need matching units; `× ÷` combine units. `spread + temperature` can't be built.
- **Evaluation:** vectorised over (day, hour, location), with sub-expression caching across the population.
- **Operators:** see §9.6.
- **Why not neural nets or a linear weight vector:** opacity and overfitting with about 20 years of data, versus no "only when" conditions (round 9).

### 9.4 Identity, names and lineage (round 19)
- **Trader id (changed round 20):** run number + birth number, e.g. `R12-184213`. Unique by construction and ordered by birth. (Round 19's 8-hex genome hash would give about 116 colliding pairs per million traders, and it confused twins: two traders with identical genes but different parents and births.)
- **Genome id:** SHA-256 of the canonical genome JSON, shown as the shortest unique prefix of at least 10 hex characters. Identical genomes share it, and the Trader page says "same genes as R9-55120"; their evaluations on the same window are reused, not repeated.
- **Behaviour id:** a hash of the trader's bids on a fixed reference window, so different code with identical behaviour is recognised. It is used to skip neutral children (§9.6) and to count **distinct behaviours** as trials in G2.
- **Name:** two words derived from the trader id (e.g. `amber-heron`). It is for memory, not uniqueness; the id is always shown beside it, and search matches either.
- **Phylogeny panel** on the Evolution page: surviving lineages, depth of the most recent common ancestor, lineage length, phenotypic volatility (Dolson et al. 2020, *Artificial Life* 26(1)). It warns when the archive descends from one recent ancestor.
- **Birth record** for every evaluated trader, in `runs/<run>/lineage.sqlite`: trader id, genome id, behaviour id, name, run, evaluation number, **generation** (lineage depth = 1 + the deepest parent's), parent ids, operator, the random seed of the operation, founder origin, the training window, fitness, niche, offspring count, alive/dead, death cause and date. About 200 bytes per trader.
- **Genomes stored** for every trader that ever entered the archive and all of its ancestors. Any other trader is **regenerated exactly** from its parents, operator and seed (runs are deterministic, §11.1), so nothing is lost.
- **Lineage crosses runs:** a Refine run (§11.5) records the parent run's trader as a parent.
- **Traders page:** search by id prefix, name, feature used, founder, operator, niche, generation, alive/dead and fitness range.
- **Trader page:** View code, tree, life, "What did it see?" (§6.4), parents (clickable), a descendants tree, and the family's improvement history (each step where a descendant beat its ancestor, and which mutation did it).

### 9.5 Starting population: founders (round 19; R19-3 in §17.3)
**Decided (round 20): mixed**, about 90 % random and 10 % named founders.
- **Random (changed round 20):** well-typed trees by **PTC2** (Luke 2000, *IEEE Trans. Evol. Comput.* 4(3)), which builds trees with a chosen size distribution: sizes spread evenly up to the slot limit. It replaces ramped half-and-half, which controls depth but not size.
- **Control run (round 20):** every reported result includes a run **without founders**, so the report shows whether founders helped instead of assuming it (seeding helps some algorithms and not others: Friedrich & Wagner 2015).
- **Human founders:** traders you write or edit (§9.1), labelled `founder:human`.
- **Founders:** hand-written traders, each tagged `founder:<name>` with its reason:

| Founder | Rule | Why |
|---|---|---|
| `always_inc` | INC at every hub-hour | mean DA − RT is slightly positive at every hub (§13); a DA premium persists in MISO (Birge, Hortaçsu, Mercadal & Pavlin 2017, MIT CEEPR WP 2017-003, read in round 18) |
| `always_dec` | DEC at every hub-hour | the mirror; profits in RT spikes |
| `persistence` | repeat the sign of the last visible spread | baseline (§12.1) |
| `premium_follow` | side = sign of `spread_mean_28d` | bets the recent average premium continues |
| `premium_fade` | the opposite | bets it reverses |
| `heat_dec` | DEC on high-`cdd_fcst` afternoons | hypothesis: hot days surprise RT upward [unverified] |
| `wind_inc` | INC when `wind_fcst × wind_cap_region` is high | hypothesis: windy days push RT down [unverified] |

- Founders are small (a few nodes) so the parsimony penalty treats them fairly.
- The report shows whether the winning lineages descend from founders or from random trees. That says whether human ideas helped.
- The O2 optimizer joins as a further seed later (§20.5).

### 9.6 Mutation and crossover (round 19)

| Part of the genome | Operator | How random |
|---|---|---|
| tree structure (`where`, `when`, `score`) | **subtree mutation**: replace a random subtree by a new random well-typed subtree | node chosen at random; new subtree by ramped half-and-half |
| single nodes | **point mutation**: swap a node for one of the same type and arity (`>`↔`<`, `+`↔`−`, a feature for another with the same unit) | uniform over the allowed swaps |
| tree size | **hoist / shrink**: replace a subtree by one of its own subtrees, removing code | bloat control (Luke & Panait 2006 compare methods, *Evolutionary Computation* 14(3), doi 10.1162/evco.2006.14.3.309) |
| two parents | **size-fair crossover** (round 20): subtrees of similar size swapped in the same slot, types matched | Langdon 2000, *Genet. Program. Evolvable Mach.* 1; limits growth. Plain subtree crossover is often no better than mutation (White & Poulding 2009, doi 10.1007/978-3-642-01181-8_19: crossover "does not significantly outperform mutation on most of the problems examined"; Angeline 1997, doi 10.1007/BFb0014804, on crossover as macromutation; checked round 27), so crossover stays a minority operator |
| constants in trees | **Gaussian**, σ = 2 %, 10 % or 30 % of the feature's historical inter-quantile range (chosen by the bandit below), clipped to its range | |
| category sets | add or remove one member | |
| numeric genes (side thresholds, price offset, size scale, risk settings) | **iso+line-DD by default** (round 20): a step along the line between two elites plus a small Gaussian (Vassiliades & Mouret 2018, arXiv 1804.03906: "directional variation" accelerates MAP-Elites) | |
| (later) all continuous genes | **CMA-ME** emitter (Fontaine, Togelius, Nikolaidis & Hoover 2019, arXiv 1912.02400) | |

- **Never mutated:** hard caps (MW cap, out-of-money rule, data visibility), the skeleton shape, the type and unit system.
- **Randomness is seeded:** NumPy PCG64, one stream per worker; the seed of each operation is stored with the child, so every mutation is random and exactly reproducible.
- **Operator rates adapt (round 20):** a multi-armed bandit picks the operator (and one of three constant step sizes: 2 %, 10 %, 30 % of the inter-quantile range), rewarding operators whose children enter or improve the archive. Each keeps a floor probability of 5 %. Basis: bandit selection of emitters in MAP-Elites improves quality, diversity and data efficiency (Cully 2021, arXiv 2007.05352); adaptive operator selection (Thierens 2005; Fialho et al. 2010). The bandit's draws are seeded, so runs stay byte-reproducible. Starting weights: subtree 0.25, point 0.20, constant 0.30, hoist 0.10, crossover 0.15. The Evolution page shows each operator's success rate.
- **Neutral children are skipped (round 20):** a child whose behaviour id equals its parent's is not evaluated; the operator retries up to 5 times.
- **Rejected:** geometric semantic operators (children grow fast and become unreadable); gradient fitting of constants (fitness is not differentiable); language-model mutation (§9.1).
- **Size limit** about 15 nodes per slot, plus the parsimony term in F (§10.2). The combination is the most effective bloat control in Luke & Panait 2006 (*Evol. Comput.* 14(3)).

### 9.7 Size gene: proposed, not adopted
- **Proposal:** g ∈ [0.05, 1], with `MW = floor_to_0.1(g × position_scale × cap)`, and 0 if below 0.1 MW.
- Mixed-direction bots would need sizing on their own trailing p99. Their tail is up to 1.56× the single-direction benchmark (full sample; median 1.41×, maximum 8.79× trailing).
- **Not added**, because F rises monotonically in g for always-INC (0.126 at g = 0.1 … 0.540 at g = 1), so the gene would likely saturate at 1.
- **Before adopting it:** invariant property tests, a saturation test on synthetic MAP-Elites runs, a planted-signal test, and a storm-avoider check (`capital_sizing.md` §7c).

---

## 10. Career model (when a bot dies) and fitness

### 10.1 Default career: an individual (round 13; death rule changed in round 19)
A one-person trading company that meets MISO's entry rules. Prop trader and hedge fund are optional presets in `configs/careers/`.

**Default death = out of money (my decision, round 19).** A trader dies when it can no longer post MISO's collateral for even the smallest possible bid (0.1 MW for one hour; `market_rules.md` §4). In practice that is equity at or near zero.
- When equity is positive but too small for the bids a trader wants, the bids are **cut to what its credit allows**. It is not killed.
- **Every other layer below is optional and off by default.** It can be switched on in the config or in a career preset.
- The exact definition (decided round 20, R19-4): (a) above. A **"MISO-eligible" preset** also kills below MISO's minimum capitalization ($500k tangible net worth for a non-FTR trader, Attachment L §III.C). The rejected alternative, equity ≤ 0, ignores collateral.
- **Consequences:**
  - with proportional sizing (§13), equity shrinks towards zero rather than through it, so deaths come mainly from single storm days (Elliott cost 31.2 % at full size);
  - far fewer traders die than under the old 2/3 floor;
  - log-growth fitness (§10.2) still punishes deep drawdowns, because ln(W) falls fast as W shrinks;
  - `capital_sizing.md`'s headroom and "lowest $50k step" numbers used the 2/3 floor, so they now describe the optional floor preset;
  - M0 step zero still runs the 40 tests unchanged; the default changes afterwards, with test updates logged.

**Capital floor vs drawdown limit: two different controls.**
- A **capital floor** is about the **level** of wealth: "below $X I may not, or should not, trade." Example: MISO's minimum capitalization. It ignores the path.
- A **drawdown limit** is about the **path**: "stop after losing Y % from my peak." It is self-discipline relative to the high-water mark.
- Example: a trader that grew to $3M and falls to $2M is down 33 % from its peak. It trips a 30 % drawdown limit while still far above a $1M floor.

| Layer | Real-world cause | Rule | Default |
|---|---|---|---|
| **L0 Out of money** | can't post collateral | as above → **death** | **on** |
| **L1 Capital floor** | eligibility or prudence | equity ≤ `effective_ruin_floor_usd()` → death. Relative floor (e.g. 2/3 of starting capital) or absolute `ruin_floor_usd` (e.g. MISO's $500k minimum capitalization); an absolute floor leaving < 10 % headroom is rejected. Basis: Attachment L §III.B–C (`market_rules.md` §5) | off |
| **L2 Personal loss limit** | "stop if I lose 40 % from my peak" | hard stop at an evolved drawdown limit | off |
| **L3 Quitting after poor results** | family, stress, doubt | monthly hazard `h = logistic(β0 + β1·cumPnL + β2·R6m + β3·DD + β4·Age)`. Fit β so that a population of *losing* baseline bots (random bots after costs) reproduces about **44 % / 24 % / 15 % survival at 1 / 2 / 3 years**. Poor results raise h; long survival lowers it. A `persistence` parameter models a stubborn trader. | off. Basis: Barber, Lee, Liu, Odean & Zhang (2020), *Learning, Fast or Slow* (Taiwanese day traders), doi 10.1093/rapstu/raz006. The working paper (Oct 2017) says "survival rates at one, two, and three years are 44%, 24% and 15%" for day traders who traded at least 10 days, losers and winners together (obs., round 27) |
| **L4 Opportunity cost and overspecialisation** | the edge is gone; T-bills pay better after fixed costs | Page's CUSUM on monthly returns in excess of (risk-free + fixed costs ÷ capital); a signal retires the bot (it also catches regime-specific bots) | off. Basis: sequential analysis |
| **L5 Peers** | – | other traders' behaviour | off for individuals; on for prop trader and hedge fund |

- **Fixed yearly costs** of running the company (audit, accounting, MISO admin charges, data): $50k/year **assumed**. M0 estimates the real amount: MISO's published participant fees (hard numbers) plus clearly labelled assumptions for the rest.
- **L3 caveat** (state it in reports): the data are Taiwanese stock day traders, not capitalised power traders. We calibrate the direction and speed of quitting, not their overconfidence.
- **Prop trader preset:** firm capital, a tight daily loss limit (e.g. 2 %), a maximum drawdown (e.g. 10 %), peers on.
- **Hedge fund preset:** an investor-withdrawal hazard calibrated to about 14 % yearly attrition for managed futures (Getmansky, Lo & Mei 2004: attrition "to a high of 14.4% per year on average for managed futures funds", TASS 1994–2004; abstract read round 27); two losing years raise the risk; peers on.
- **Citation status:** the earlier "Chan, Getmansky, Haas & Lo 2005" logit citation and "Brown, Goetzmann & Park 2001" were **not** verified in Claude Science. One was flagged as unsupported by the reviewer. Verify them or drop them.

### 10.2 Fitness
$$F = \mathbb{E}_{\text{career}}\big[\ln(W_T/W_0)\big] - r_f T - \mu\cdot\text{size}$$
- Expected log-growth of the account in excess of the risk-free rate, under the career model, minus a small parsimony penalty on formula size.
- **Log-growth punishes over-leverage by itself:** growth ≈ μ − σ²/2, so excess growth is zero at 2× Kelly and negative beyond.
- **L3 enters as an expected survival probability** `S = ∏(1 − h_t)`, so fitness stays deterministic (when L3 is switched on). L0 and, when switched on, L1, L2 and L4 are hard stops.
- **QD gives choice, not protection.** Risk control comes from fitness and the career model.
- **Storm sensitivity** (reporting only, `storms.py`): F with and without Uri (2021-02-15..19) and Elliott (2022-12-23..25).

---

## 11. Quality-diversity search: MAP-Elites

- **Map** (2-D grid, shown as a heatmap):
  1. **Net direction:** (DEC MWh − INC MWh) ÷ total cleared MWh, from −1 to +1.
  2. **Selectivity:** the fraction of visible location-hours traded, on a log scale.
- **Possible later third axis:** location concentration (CVT-MAP-Elites).
- **Loop:**
```
archive = {}                                  # cell → best bot
seed with N random bots
repeat until the evaluation budget is used or the session time ends:
    children = [mutate_or_crossover(select_parents(archive, selection_pressure))   # §11.2
                for _ in range(batch)]
    for child in evaluate_parallel(children, window):     # current 5-year training window
        if child.dead: continue                            # natural selection
        cell = descriptor_to_cell(child)
        if cell empty or child.F > archive[cell].F: archive[cell] = child
    when the window moves: re-evaluate every elite on the new window, re-decide cells   # round 20
    every ~10 min: checkpoint
```
- **Training window (changed round 20): 5 years, rolling, stepped by 1 year** through 2005–2025; each elite is also scored on the next unseen year (walk-forward). It was 1 year, after the virtual-bidding papers (4 of 8 use ~1 year), but:
  - those papers re-estimate a forecasting model online, a different task from selecting fixed rules;
  - the standard error of an annualised Sharpe ratio is about 1/√years: ≈ 1.0 on 1 year, ≈ 0.45 on 5;
  - this briefing's MinBTL table allows ~3 independent trials at Sharpe 1 on 1 year versus ~45 on 5.
  - Cost: about 5× fewer evaluations per hour at the same trader-years per hour. `training_window_years` stays configurable; O8 compares 1, 3 and 5 years at equal compute (`docs/design_rationale.md` C1).
- **Fair comparisons (round 20):** when the window moves, every elite is re-evaluated on the new window before any child is compared with it. Otherwise a child scored on one window would be judged against an elite scored on another. Elitist QD handles noisy fitness badly (Justesen et al. 2019); "deep grids" (Flageat & Cully 2020) are an O8 option (`docs/design_rationale.md` C2).
- **Optional later:** CMA-MAE emitter for continuous parameters; multi-fidelity racing (successive halving).

### 11.1 Long runs on a laptop
- `evobots run config.toml --hours 3` runs, checkpoints and exits; `evobots resume runs/<id>` continues.
- **A checkpoint every ~10 minutes** holds the archive, RNG states, evaluation counter and window schedule.
- **Determinism:** a resumed run must be **byte-identical** to an uninterrupted one. This is tested.
- **Progress is counted in evaluations**, not wall-clock.
- **Deployable bot at any time:** after each checkpoint, quick gates (G1, G2, G4, G6) run on the top elites. The best passing bot goes to `runs/<id>/deployable/current_bot.json`; if none passes, the file says **"do nothing"**.
- **Overfitting guard that grows with compute:** the deflated Sharpe uses the true evaluation count, and the hold-out is opened once.

### 11.2 Reproduction: who gets offspring (round 19; R19-1 in §17.3)
- **Plain MAP-Elites** (Mouret & Clune 2015, arXiv 1504.04909) picks parents **uniformly at random** from the elites, and a child takes a cell only if it beats the incumbent. Profit then matters only through being an elite or not: an elite with ten times another's profit gets **no more offspring**.
- **Decided (round 20): rank-weighted selection with a selection-pressure knob p ∈ [0, 1].**
  - P(elite i is chosen) = (1 − p) · uniform + p · rank weight, where the rank weight grows with the elite's fitness rank.
  - p = 0 is plain MAP-Elites; proposed default p = 0.5.
  - More profitable traders then get more offspring. The Trader page shows each trader's offspring count.
- Alternatives: uniform only; "curiosity" (favour elites whose children tend to enter the archive), the "curiosity score" of Cully & Demiris 2017 (arXiv 1708.09251, §III-B3: a parent gains 1 when its child enters the archive and loses 0.5 otherwise; read round 27); and wealth-driven reproduction in market time (Life mode, §11.3).
- **When and how often:** continuously, in batches (§11 loop) for as long as the run lasts. O8 compares uniform, rank-weighted and **ε-lexicase on per-year results** (La Cava et al. 2016; Helmuth et al. 2015), which favours parents that are best on random subsets of years, at equal budget.

### 11.3 Compute time vs market time; how many generations (round 19)
- **Evolution runs in compute time, not market time.** Each evaluation replays one trader over a rolling 5-year window of history (plus the next year for walk-forward). The window steps through 2005–2025 as the run goes on. A single trader does not live through decades or reproduce mid-history.
- **Why decades take seconds** (explanation; numbers are estimates until the M3/M6 benchmarks):
  - history is recorded, so nothing waits for markets;
  - traders are price-takers and don't interact, so each replays independently and in parallel;
  - a hub trader-year is 8 × 24 × 365 = 70,080 location-hours of simple vectorised arithmetic.
  - The target of 100,000 trader-years per hour on 20 cores (§14.3) is about 28 per second.
- **Generations.** MAP-Elites has no strict generations, so the app shows two counters, both explained on screen:
  - **batches done** (about 20 per hour at the target speed with ~1,000 children per batch on 5-year windows; estimate);
  - **lineage depth**, the longest chain of ancestors (§9.4).
- **Life mode (M6b, decided round 20):** a market-time ecology.
  - A population lives through 2005-04 → 2025-09 day by day. Each trader trades every day it is alive and dies when out of money (§10.1).
  - It **reproduces when its equity reaches k × its starting capital** (proposal k = 2), handing starting capital to a mutated child.
  - A child trades only from the day after its birth, so its whole career is out-of-sample relative to its creation.
  - Generations are limited by market time: a trader that doubles every 2–5 years gets about 4–10 generations in 20 years (arithmetic, not measured). That is too few for search, but it is the literal natural selection of §1.1 and an honest realism check.
  - Related work: the Santa Fe artificial stock market (Arthur, Holland, LeBaron, Palmer & Tayler 1997, doi 10.2139/ssrn.2252), whose traders interact (ours don't); Lo 2004, *The Adaptive Markets Hypothesis* (doi 10.3905/jpm.2004.442611).
  - MAP-Elites stays the search engine; Life mode is a showcase and a comparison on the leaderboard.

### 11.4 The best bot (round 19)
- **Best** = the highest **out-of-sample** (walk-forward) fitness F among elites that pass the quick deployment gates G1, G2, G4 and G6; ties go to the smaller program. It is **not** the highest in-sample profit, which is usually the most overfitted trader.
- A **Best bot** link at the top right of every page opens its Trader page, with a table of why it beat the next five candidates.
- If none passes, the page says **"Do nothing: no trader passes the gates"**, and names the nearest candidate and the gate it failed. `current_bot.json` holds the same thing (§11.1).

### 11.5 Refine runs (round 19)
- A **Refine** button on any Trader page starts a new run seeded with that trader and mutants of it, on the evolution period **2005-04 → 2025-09 only**. Options: stay in its niche, or open the whole map.
- Lineage continues across runs (§9.4).
- **Trial counts carry over:** the deflated Sharpe counts every trial in the parent and child runs, because refining is more searching.
- **If the trader's sealed test was already opened** (§12.4), the refine run is labelled **"hold-out already used"**: its sealed-test result no longer counts as clean. The only clean test left is forward data (2026-09-22 onward, growing daily), via the **Forward test** button.

### 11.6 The grid map explained (round 19)
- **Horizontal axis:** net direction, from −1 (only INC: always selling in DA, betting DA > RT) to +1 (only DEC).
- **Vertical axis:** selectivity, the share of available location-hours the trader bids on, log scale from 0.1 % to 100 %.
- **Each cell** holds the best surviving trader of that kind. **Colour** = its fitness F on a colour-blind-safe sequential scale. A **blank (white) cell** means no surviving trader of that kind has been found yet.
- **Click** opens the trader; **hover** shows name, F, profit and trades per day.
- A switch recolours by profit, maximum drawdown, lineage depth or founder origin.
- **What it tells you:** how many different kinds of strategy survive, where the profitable ones are (e.g. "selective INC traders"), and which kinds are empty. A legend and a short "how to read this map" note sit next to it.

---

## 12. Evaluation: baselines, report card, literature

### 12.1 Baselines (fixed anchor bots)
- do nothing;
- 1 MW at one hub;
- always INC at every hub;
- always DEC at every hub;
- persistence (repeat the sign of the last visible spread);
- random bots with matched trading frequency.

### 12.2 Gates

| Gate | Test |
|---|---|
| G1 Survival | survival over 1,000 stationary block-bootstrap paths of the validation period (document the block-length choice) |
| G2 Skill vs trials | deflated Sharpe ratio with the **effective** number of trials (cluster or PCA the bots' daily P&L streams), plus the MinBTL bound |
| G3 Overfitting | probability of backtest overfitting (CSCV) across the archive |
| G4 Cost stress | still profitable with fees and uplift doubled |
| G5 Scale-up | re-scored on all locations (stage C) and at the MW cap |
| G6 Walk-forward | positive growth in next-period tests; drawdown within the mandate |
| G7 Shock periods | results per event-calendar period (COVID, Uri, Elliott, the 2022 gas crisis, the 2026 Iran war, …) and per global-gas-shock month |
| G8 Hold-out | the sealed 12 months, once, at the end |

- **Output:** `assess/report_card.py` returns **JSON**. One renderer draws it in the app and exports a single self-contained HTML file. This replaces the spec's separate matplotlib `report.html`; confirm with me.
- **Report contents:** gates, equity, drawdown, MW by location type, features read, shock-period results, the with/without-storms F, the hindsight check, global gas context (World Bank), and an honest-expectation note.

### 12.3 What the literature says (round 5; `virtual_bidding_literature.csv`)
The 8 arXiv papers were downloaded and read in full, and 24 quotes were checked against the text:
- 1703.02567 (NYISO)
- 1802.03010 (NYISO, PJM)
- 2012.00076 (CAISO: of 2,265 nodes, only 475 ever held a convergence bid)
- 2104.02754 (PJM, ISO-NE, CAISO; CAISO the least efficient)
- 2109.09238 (CAISO)
- 2210.06543 (CAISO, correlation clustering)
- 2303.02303 (CAISO)
- 2412.00062 (ERCOT, assumes $5/MWh costs)

Only two model fees or uplift; the rest use the raw spread, which flatters results.

**MinBTL** (my reimplementation of Bailey et al. 2014, unchecked against the paper): independent trials allowed at Sharpe 1 / 2 are 3 / 25 for 1 year, 15 / 3,265 for 3.2 years, 45 / 145,785 for 5 years, and 724 at Sharpe 1 for 10 years. For the option-D history (20.5 in-sample years), about 187,000 at Sharpe 1.

**Lessons from the 11 papers in my folder** (`paper_digest.md`):
- the better the validation and cost model, the weaker the result;
- a three-way split is the minimum;
- costs belong in the fitness (train at a higher cost than the test cost);
- parsimony pressure matters;
- report distributions over seeds, not the best run;
- compare against random-rule and bootstrap nulls;
- edges decay, so use walk-forward.

### 12.4 The sealed 12-month test in practice (round 19)
- **Button:** **Final test (sealed 12 months)** on the Trader page of a run's chosen trader (normally the best bot, §11.4).
  - A confirmation explains that it can be used once per run and is logged.
  - The result page puts sealed-test metrics next to the walk-forward metrics, with the "What happened" summary (§15.2).
- **Separation from training, enforced in code:**
  1. the hold-out (2025-09-22 → 2026-09-21) is a separate file under `data/holdout/`;
  2. only the `final_test` module knows its path;
  3. evolution workers are given a data root that doesn't contain it;
  4. a test fails if any other module imports the hold-out reader or opens that path;
  5. every opening is logged (who, when, run, trader).
- **Status is visible:** the Home page shows "Sealed: never opened" or "Opened on <date> for <trader> in <run>".
- **Once seen, it's spent for that lineage:** a run that refines a trader whose sealed test was opened is labelled "hold-out already used" (§11.5). The **Forward test** (2026-09-22 onward) stays clean and grows every day.

---

## 13. Capital and sizing (built; reproduce these numbers)

- **Defaults** (`CapitalSettings`):

| Setting | Default | Range / note |
|---|---|---|
| `starting_capital_usd` | $1,500,000, **final default (round 25)**; always editable | $250k–$5M, step $50k (Stage A) |
| `daily_risk_budget_fraction` (was `daily_risk_budget`) | 0.02 | 0.005–0.05 |
| `credit_share_fraction` (was `credit_share`) | 0.25 | 0.05–0.80 |
| MPD | from market data, ≥ 12 | no longer a setting (§13.1); collateral functions take it as an argument |
| `max_mw_per_hub_hour` | 5.0 | |
| `ruin_floor_fraction` | off (round 19; the round-16 preset is 2/3) | 0–0.9 |
| `ruin_floor_usd` | none | optional absolute floor |

- **Sizing rule:** `position_scale = min(1, daily_risk_budget × equity / trailing_p99_full_size_daily_loss)`.
  - The trailing window is 365 days, newest usable day D−6, with a 90-day warm-up (returns None → scale 0 → no trades).
  - The full-sample value `CALIBRATION_ONLY_FULL_SAMPLE_P99_USD = 27_897` lives only in `cli.py`, and a test keeps it out of simulation code.
- **Liquidity cap:** `min(5 MW, 5 % of the hub's median cleared virtual MW)`, rounded to 0.1 MW. That gives 5 MW at seven hubs and **4 MW at MS.HUB**. **Full size = 39 MW × 24 = 936 MWh/day** (not 960; a test checks this).
- **Hub medians (cleared virtual MW per observable hub-hour):** ARKANSAS 161.2, ILLINOIS 490.1, INDIANA 707.6, LOUISIANA 175.3, MICHIGAN 366.7, MINN 423.3, MS 79.0, TEXAS 160.25. Only 25–48 % of hub-hours were observable, because a bid is attributed to a hub only when the hub uniquely has that ex-ante price and the Region field is blank.
- **Anchor numbers to reproduce** (2019-01 → 2025-09, 8 hubs):
  - mean spread s = DA − RT is slightly positive at every hub ($0.04–0.96/MWh); median |s| $2.6–4.7; std $30–62; excess kurtosis 560–3,300;
  - always-INC full size: mean day +$474; 1-in-100 day loss $27,897; worst day **$492,173 (2022-12-23, Elliott)**;
  - always-DEC: 1-in-100 day loss $19,351; worst day **$176,554 (2021-02-18, Uri)**;
  - C_full = 27,897 ÷ 0.02 = **$1.39M** (full sample); point-in-time $0.52M–$2.24M, median $1.21M;
  - trailing p99 breach rate **2.2 %** of days (2022: 4.7 %); 2015-06 → 2018-12: 1.38 %;
  - at $1.5M: headroom 33.3 % vs worst 20-day loss 24.6 %; full size on 80.6 % of days; the Elliott day costs 31.2 %;
  - storm F at $1.5M: always-INC 0.540 → 0.684 without storms (Elliott −0.212, Uri +0.069); always-DEC −0.411, ruined 2022-01-21;
  - lowest $50k step passing all conditions: $1.40M with the absolute $1M floor; $1.10M with the relative floor;
  - fixed cost per MWh at $1.5M: $0.146 (full volume), $0.203 (72.1 % cleared), $0.585 (25 %);
  - explorer expected values: `capital_sizing.md` §10.

### 13.1 Who sets each value (round 19)
Every value in the app and the config carries one of three badges. Only **Your choice** values are editable.

| Value | Badge | Note |
|---|---|---|
| `starting_capital_usd` | **Your choice** | |
| `daily_risk_budget` | **Your choice** | how much risk to take per day |
| `credit_share` | **Your choice** | share of capital pledged as collateral (default 25 %); it sets the Virtual MWh Limit, which never binds at Stage A but will at stages D and C (decisions log, round 14) |
| `max_mw_per_hub_hour` | **Your choice** for the 5 MW cap and the 5 % share; **From market data** for each hub's median cleared MW | |
| `ruin_floor_fraction`, `ruin_floor_usd`, drawdown limit, quit hazard, CUSUM | **Your choice**, off by default | §10.1 |
| `mpd_usd_per_mwh` | **From market data** (was a user input) | computed by Attachment L's formula: 50th-percentile DA−RT differential over the prior 12 months, reset each May 1, floor $12 (`market_rules.md` §4.1) |
| Schedule 17/24 fees, RSG rates | **From market data** (were constants) | cost table by month and era (§6.2); "estimate" until the Rates Factors file arrives |
| Risk-free rate | **From market data** | FRED's 3-month T-bill rate (DTB3, Federal Reserve H.15, public domain; decided round 28) |
| Fixed yearly costs ($50k) | **Your choice**, labelled **assumption** | round 18 found no fixed MISO fee; it covers audit, accounting, legal |
| Collateral, Virtual MWh Limit, position scale, trailing p99 loss | **From the trader's account** | computed from its own bids and P&L |

---

## 14. Engineering standards (apply to every milestone)

### 14.1 Natural naming
- Full words. Abbreviate only with the approved list: DA, RT, LMP, MW, MWh, INC, DEC, MPD, RSG, VMEW, ISO, MISO, EIA, NWS, EPU, GPR, HDD, CDD, pnl, p99, QD, GP, CUSUM, PBO, CSCV, id, config.
- **Units in names:** `_usd`, `_mw`, `_mwh`, `_usd_per_mwh`, `_days`, `_hours`, `_fraction` (never percent in code), `_degf`.
- **Functions:** those returning a value are named for what they return (`trailing_p99_daily_loss`); those doing something are verb phrases (`build_price_store`).
- **Other names:** booleans start `is_`, `has_` or `can_`; collections are plural; mappings are `value_by_key`; constants are UPPER_CASE with a unit.
- **One word per idea everywhere;** `docs/glossary.md` is the dictionary.
- Maths symbols stay in `maths.md`; docstrings map words to symbols.
- **Enforcement:** ruff with pep8-naming, plus `tests/test_naming.py` and an editable `naming_allowlist.txt`.
- **Naming pass in M0, with behaviour unchanged and all 40 tests passing:**
  - `s`, `g`, `w` in `cli.py`;
  - `pts`, `c0, f0, c1, f1`, `out` in `capital.py`;
  - `v`, `d` in `sizing.py`;
  - `C, rb, F, ff, absF, q, D` in the explorer.

### 14.2 Documentation (Diátaxis: four kinds)

| Kind | Where |
|---|---|
| Tutorial | `docs/tutorial.md` (M9; stub at M1.5) |
| How-to guides | `docs/how_to/`: change default capital; add a feature; add a GP primitive; add a career preset; change colours and fonts; add a page; add a chart; add a data source; run offline; export a bot |
| Reference | generated from docstrings, plus `docs/config_reference.md` (every TOML key: meaning, unit, default, bounds, source) |
| Explanation | `maths.md`, `market_rules.md` (M0); `data_sources.md` (M1); `features.md` (M2); `qd_explained.md` (M6); `report_card.md` (M7); `architecture.md` (M1.5); `glossary.md`; the round docs and the decisions log |

- **Every public function** has a fixed-format docstring: summary; arguments with units; return value with unit; "Maths:" and "Decision:" pointers; an example. Comments explain why and cite their source.
- **Formula ↔ function ↔ test are linked three ways.** The test's numbers are `maths.md`'s worked example.
- **Docs are tested:** doctests in modules and in `*.md`, an internal-link checker, and ruff docstring rules.

**Complete documentation and the change ledger (my decision, round 19):**
- **`docs/design_rationale.md`:** the logic behind every decision: literature, options, pros and cons, status. Updated with every decision (round 20).
- **`docs/change_ledger.md`:** one row per change (date, round, commit, what changed, why, files, decision link), updated with every commit. A test checks that every round doc is listed.
- **Every module, class and function, public and private,** has a docstring in the fixed format above.
- **Every constant** has a comment: meaning, unit, source.
- **Every config key** is in `config_reference.md`.
- **Every library** is in `docs/dependencies.md`: purpose, licence, version.
- **Every input and output file** is in `data_sources.md` or the file-format reference.
- **Every dataclass field** is documented.
- **A generated symbol index** (`docs/reference/`) lists every module, function, class and constant with its purpose. A test fails when one lacks documentation.
- **Local variables** are explained by full-word names (§14.1) plus comments where not obvious, not by one doc entry each (decided round 20, R19-6): one entry per local would roughly double the code and drift out of date.

### 14.3 Efficiency
- Measure, don't guess: `benchmarks/run.py` appends to `benchmarks/results.csv` every milestone. Profile before optimising.
- **A readable reference plus a fast version**, with an agreement test on random inputs (e.g. the Numba engine against a plain-Python reference).
- **Compute once and reuse:** memory-maps, features computed once, sub-expression caches, parallel cores, Numba `cache=True`.
- **The UI never does heavy work.** A worker process handles long jobs. Series are thinned on the server to ≤ 2,000 points, keeping each bucket's min and max so spikes survive.
- **Targets** (proposed; confirm with me):

| What | Target |
|---|---|
| Hub-stage evolution | ≥ 100,000 bot-years/hour on 20 cores (a hub bot-year ≈ 8 × 24 × 365 ≈ 70,000 location-hours) |
| `serve` to first page | ≤ 3 s |
| Any page's data request | ≤ 300 ms |
| UI server memory | ≤ 500 MB |

### 14.4 Offline
- Nothing needs the internet at run time.
- The network-using actions are named, optional and labelled "needs internet", each with an offline alternative: `data build --download` (or drop archives into `data/inbox/`), `paper fetch`, first install.
- **No CDN scripts, web fonts, telemetry or update checks.** Third-party browser files are vendored in `app/static/vendor/`, with `VENDORED.md` (version, licence, SHA-256). FastAPI's built-in docs page loads from a CDN, so switch it off.
- **Enforcement:**
  - the whole suite runs under pytest-socket (localhost only);
  - Playwright page tests run with non-localhost requests blocked;
  - a static test rejects `http(s)://` in templates outside an allowlist.

### 14.5 UI you (I) can easily edit
- **Option A (recommended):** FastAPI + Jinja2 templates, one `theme.css` (every colour, font, size and spacing as a named variable, light and dark), one small script per page, `pages.toml` for navigation. No Node and no build step.
- **Option B:** NiceGUI, Python only.
- **Rules:**
  - one place per kind of change;
  - **the UI never computes results** (it calls `service.py`; this retires the explorer's duplicated JavaScript formulas and the Python twin `explorer_expected()`);
  - every template starts with a comment naming its endpoints and doc section;
  - a component gallery page;
  - `serve --dev` live reload;
  - a colour-blind-safe palette;
  - keyboard access;
  - a screenshot per page on each test run.
- **Not Streamlit or Gradio:** full reruns, limited layout, telemetry and font workarounds.

**UI separated from everything else (my decision, round 19):**
- All presentation lives in `src/evobots/app/`: `server.py`, templates, `theme.css`, page scripts, `pages.toml`, vendored files.
- **Enforced by an import test:** `evobots.app` may import only `evobots.service`; no trading, accounting, data or evolution module may import `evobots.app`. Templates and page scripts contain no formulas (§18).
- `docs/how_to/change_the_ui.md` says which single file to edit for each kind of change (colour, font, spacing, label, page, chart, navigation).

**Visual style (my decision, rounds 19–20): minimally colourful and fully utilitarian.**
- **Reference:** `docs/design/visual_reference/reference_dashboard.png` (supplied in round 20), made **simpler and less colourful**. Reasons in `docs/design_rationale.md` part E.
- **Taken from the reference:**
  - a left navigation of text items with nested sub-items;
  - page title with search and the **Best bot** link at top right;
  - one line of filters and actions as plain words;
  - every metric and chart as **title, one-line plain-English description, then value or chart**. That is the explanation rule of §15.2.
- **Changed from the reference:**
  - **white everywhere**: no black sidebar, no grey backgrounds, fills or panels;
  - sections separated by whitespace and 1-px hairlines, square corners, no shadows or gradients;
  - **no button boxes: every action is a clickable word**, underlined on hover; the search field is a single bottom rule;
  - charts and the grid map in **ink and greys only**; one signal colour (muted red) reserved for losses and deaths;
  - no icons except a "?" for help.
- **Tokens** (`docs/design/theme.css` now, `app/static/theme.css` at M1.5): ink `#111111`, secondary text `#5f5f5f`, hairline `#e4e4e4`, background `#ffffff`, signal `#a3271f`; system fonts only; type 12/14/16/22 px; spacing 4/8/16/24/40 px; numbers in tabular figures.
- **Preview on real data:** `docs/design/preview_data_page.html`, built by `tools/build_design_preview.py` from the downloaded archive. Static HTML and inline SVG; no JavaScript, no network requests (checked headlessly, round 20).
- A dark theme is optional and later; the light theme is the reference.

### 14.6 Single-file deliverables (proposed; needs my confirmation)
1. **Engine:** `evobots build-single-file` → `evobots-<version>-<os>.pyz`, built with `shiv` (code, dependencies, bundled data).
   - Run: `python evobots-….pyz serve`.
   - Windows first.
   - Check that Numba's cache works from the unpacked location.
   - No PyInstaller .exe: it hides the code.
2. **Each bot:** `evobots export-bot <id>` → `bot_<id>.py`, standard library only, containing only the features it uses.
   - The input spec is at the top of the file. Run: `python bot_7c2e.py --inputs today.csv`.
   - **Equivalence test:** on many random days, the file's bids equal the engine's exactly.

### 14.7 Definition of done (every milestone)
- [ ] Tests pass, including look-ahead, determinism and equivalence tests where they apply.
- [ ] The full suite passes **with networking blocked**.
- [ ] ruff and the naming test pass.
- [ ] New public functions have docstrings; new formulas are in `maths.md` with the worked example as a test.
- [ ] Explanation docs, how-to guides and glossary terms are written; doc tests pass.
- [ ] Benchmarks are appended; any missed target is explained.
- [ ] From M1.5 on, the app page passes the offline browser test, and its screenshot has been looked at.
- [ ] Round doc written, decisions log and workflow status updated, committed.

---

## 15. The app (local, offline, browser-based)

```
browser page (template + theme.css + page script + vendored charts)
        │  JSON over localhost only
        ▼
server.py   routes only
        ▼
service.py  the single bridge: validates input, calls the core, returns plain data
        ├──► core: data · features · market · bots · career · qd · assess · deploy
        └──► worker process (evolution runs, data builds, report cards) → checkpoints + status.json
```

| Page | Arrives | Shows / does |
|---|---|---|
| Home | M1.5 | data status, runs, deployable bot, which actions need internet |
| Capital | M1.5 | replaces `capital_explorer.html`; sliders call `CapitalSettings`; save to config |
| Docs | M1.5 | all docs with search, KaTeX maths, "?" deep links |
| Gallery | M1.5 | every component in the current theme |
| Settings | M1.5, grows | edits config with the CLI's validation |
| Data | M2 | coverage, prices, feature distributions with units |
| Simulator | M3 | baselines against `capital_sizing.md`'s numbers |
| Traders | M4 (lineage from M6) | search by id, name, feature, founder, operator, niche, generation, alive/dead, fitness (§9.4) |
| Trader | M4, grows | View code, tree, printed rules, life, "What did it see?", parents and descendants, offspring; actions (words) Refine, Final test, Forward test, Download |
| Career | M5 | survival-curve fit, outcomes, storm sensitivity |
| Evolution | M6 | start/resume/stop, progress, heatmap, deployable bot |
| Report card | M7 | gates and charts; export to one HTML file |
| Paper trading | M9 | today's bids, ledger, running P&L |
| Scenarios | O1 (§20) | fitted price models, simulated vs real spread distributions, stress scenarios |
| Optimizer | O2 | the optimization-based bidder: today's optimal bids, the efficient frontier, its backtest |
| Portfolio | O3 | CVaR portfolio of elites: weights, frontier, rolling out-of-sample results |
| Battery | O4 | storage policies: state of charge, profit vs the perfect-foresight bound |
| Risk | O5 | VaR/ES estimators side by side, backtest test results, tail plots |
| Methods leaderboard | O7–O8 | every strategy class on the same windows, costs and gates |
| Life | M6b | the market-time ecology: population over 2005–2025, births, deaths, family trees |

### 15.1 Actions that must be obvious (round 19; all are clickable words, round 20)

| Button | Where | Does |
|---|---|---|
| **Best bot** | top right, every page (a word, not a box) | opens the best bot's Trader page (§11.4), or the "Do nothing" page |
| **View code** | Trader page | shows the generated source file (§9.1); Download |
| **What did it see?** | Trader page | inputs and bids for any chosen day (§6.4) |
| **Parents / Descendants** | Trader page | lineage navigation (§9.4) |
| **Refine** | Trader page | new run seeded with this trader (§11.5) |
| **Final test (sealed 12 months)** | Trader page of a run's chosen trader | the once-per-run sealed test (§12.4) |
| **Forward test** | Trader page | scores on data after 2026-09-21, always allowed |

### 15.2 Explaining results and controls (round 19)
- **Every metric, setting and outcome** has:
  - a plain-English one-liner, its unit and why it matters;
  - a formula link into `maths.md`;
  - a "?" tooltip fed from `docs/glossary.md`. One source, so the app and the docs never disagree.
- Every setting shows its badge (§13.1).
- **"What happened"** opens every result page (trader, run, report card, sealed test). It is a paragraph written from templates by Python: deterministic, no language model, no formulas in JavaScript. Example of the form: "amber-heron made $412k over 2019–2024; 70 % came from INC bids at Indiana hub on summer afternoons; it died on 2022-12-23 (Winter Storm Elliott) when …"
- Every chart has a one-sentence "how to read this" note (e.g. the grid map, §11.6).

- The CLI stays a full alternative.
- A desktop window via pywebview is optional and later.
- No multi-user or cloud version.

---

## 16. Milestones (strictly ordered unless noted)

**M0. Rules, maths, standards, fixes**
- Run the 40 tests first.
- Resolve the [verify] list against MISO's documents: bid deadline; admin fee and RSG rates; holiday list; published MPD; settlement timing; preliminary-RT archive depth (probe the server); IMM volume limits; whether Attachment L v56.0.0 is current; the individual's fixed yearly costs.
- Check redistribution terms for every bundled source.
- Write `docs/market_rules.md` and `docs/maths.md`. Every formula gets a worked example, its function and its test.
- Standards tooling: ruff config, `test_naming.py`, pytest-socket, doctests, link checker, `benchmarks/run.py`.
- Docs skeleton; seeded glossary; `config_reference.md`.
- The naming pass.
- Fix `capital_explorer.html` and add a Playwright test that fails on any console error.
- Record my four decisions.
- Mark the $1.5M default final in the spec.
- **Done when:** no [verify] markers remain (or each remaining one is explicitly accepted by me), the 40 tests pass after renames, the new checks pass, and the explorer loads cleanly.

**M1. Data builder (the long pole)**
- `data/sources/`: `miso_eras.py` (one reader per era, same normalised schema, date-range dispatch), `nws_pfm.py`, `eia_gas.py`, `epu.py`, `gpr.py` (reporting), `eia860m.py`, `worldbank.py` (reporting), `asos.py` (reporting).
- `build.py`: resumable, checksummed, offline by default, `--download` explicit, `data/inbox/`.
- `store.py` (yearly memory-maps plus `locations.csv`), `visible.py`, and `synthetic.py` (random walk / GARCH / regime switching, with an optional planted rule).
- The hold-out split and its logged accessor; `manifest.toml`; `docs/data_sources.md`.
- Settle the hub→office table.
- Round 20 head start: the MISO price archive is downloaded and parsed by `tools/fetch_miso_prices.py` and `tools/build_miso_hub_prices.py` (§7.0); M1 moves this logic into `src/evobots/data/sources/miso_eras.py` with tests, and adds the other sources.
- **Done when:**
  - `evobots data build --stage A` runs offline from bundled files and reproduces `hub_price_stats.csv` and `hub_volume_stats.csv`;
  - the look-ahead test passes;
  - the hold-out is sealed.

**M1.5. App shell.** Needs M1 and my UI decision.
- `service.py`, `server.py`, templates, `theme.css`, vendored libraries.
- Pages: Home, Capital, Docs, Gallery, Settings. Theme from the visual reference if supplied (§14.5), white surfaces, the badges of §13.1 and the explanations of §15.2 from the first page on.
- `serve`, `--dev`, the worker scaffold, offline browser tests, `architecture.md`, UI how-to guides.
- **Done when:** I change a colour and a label myself and see both change.

**M2. Feature layer**
- The catalogue (25 features, display names, units), price/weather/region features, the Data page, `docs/features.md`.
- **Done when:** all 25 features are computed, unit-tagged and look-ahead-clean, and their 2005–2025 distributions show no unexplained breaks (unit errors, a source going stale, format-swap steps).

**M3. Market simulator**
- `clearing.py`, `fees.py`, `collateral.py`, `settlement.py`; a Numba engine plus a Python reference with an agreement test; `batch.py`; the Simulator page.
- **Done when:** the baselines reproduce `capital_sizing.md` §4 and §7b, and the speed benchmark is recorded.

**M4. Bot representation**
- Units, primitives, trees, skeleton, printing, JSON, operators (§9.6), the Traders and Trader pages.
- Round 19 additions: the **source-code generator** and its equivalence test (§9.1); ids and names (§9.4); the founders (§9.5); the View code and "What did it see?" panels.
- **Done when:**
  - the planted-signal test passes (the GP recovers a planted rule and finds nothing in pure noise);
  - JSON round-trips exactly;
  - every trader's generated file gives exactly the engine's bids on many random days.

**M5. Career model and fitness**
- **Out-of-money death (L0, the default)** and credit-limited bid cutting (§10.1); the optional layers: capital floor, loss limit, quit hazard (fitted, with the fit quality reported), CUSUM (documented threshold); presets as frozen dataclasses; fitness; the Career page.
- **Done when:** with only L0 on, out-of-money deaths are reported with their dates and causes; with the quit hazard on, losing baselines give about 44 / 24 / 15 % survival; fitness is deterministic.

**M6. MAP-Elites**
- Archive, descriptors, operators, loop, checkpoints; the worker process; the Evolution page; `qd_explained.md`.
- Round 19 additions: the lineage store (§9.4), parent selection with the pressure knob (§11.2), the batch and lineage-depth counters (§11.3), the Best bot button (§11.4), Refine runs (§11.5), the explained grid map (§11.6).
- **Done when:**
  - a short hub run fills the archive;
  - any trader's ancestors and descendants can be browsed, and a non-stored trader regenerates exactly from its birth record;
  - resume is byte-identical;
  - `current_bot.json` updates, with "do nothing" as the fallback;
  - the UI stays responsive during a run.

**M6b. Life mode (decided round 20).** The market-time ecology of §11.3, its page, and a leaderboard row.
- **Done when:** a population runs through 2005-04 → 2025-09 with births, deaths and family trees recorded, deterministically.

**M7. Report card**
- `windows.py`, `bootstrap.py`, `deflated_sharpe.py`, `pbo.py`, `stress.py`, `report_card.py` (JSON); the Report page; HTML export.
- **Done when:** a full report card exists on at least one real bot. Check in with me before treating it as meaningful.

**M8. Scale up**
- Stage D (clustered representatives, yearly), then Stage C (the full memory-mapped store).
- Re-run M2–M7 and re-benchmark. Fix any hidden "8 hubs" assumption at its source.
- App: stage selector, pagination, server-side thinning.

**M9. Paper trading, packaging, single files**
- `daily_fetch.py` (optional internet) or inbox; `paper_ledger.py`; the Paper page.
  - The daily job also archives each day's EPU, GPR and Henry Hub files as true point-in-time vintages.
- `export-bot` with the equivalence test; the `.pyz`; the offline bundle if I choose it; a final UX pass; the tutorial and README tested step by step.

**Later:** CAISO adapter (check against published CAISO results, and the fallback feed); GPU backend; CVT third axis; NYISO generality check. Multi-instrument trading (futures, options, swaps) is **not planned** unless I reopen it.

**ORFE track:** modules O0–O9 in §20 run alongside M1–M9. §20.10 gives the order and which main milestone each one depends on.

---

## 17. Open decisions

### 17.1 Ask me these at the start (one multiple-choice prompt)
1. **UI editing language:** A, HTML/CSS/JS with no build step (recommended), or B, Python-only NiceGUI.
2. **Offline scope:**
   - (a) offline once installed; first install may download packages (the round-1 decision);
   - (b) also install offline, from a per-OS bundle with the Python installer and wheels.
   My later wording suggested (b). Confirming it changes the round-1 decision.
3. **Single-file deliverables:** accept the `.pyz` engine and the standard-library bot file (§14.6), or tell me what I mean instead.
4. **Performance targets** (§14.3): accept or adjust.

**Answered in round 17:** 1 → A (FastAPI + Jinja2 + one `theme.css`); 2 → (a); 3 → exported bots are standalone standard-library files, the equivalence test applies, and whether the engine ships as a `.pyz` is asked at M9; 4 → accepted.

### 17.2 To resolve during the work (propose with evidence, then ask)
- The M0 [verify] list (§16, M0).
- The hub→NWS office table (§7.4).
- The CINERGY→INDIANA rename date and node-set check.
- The CUSUM threshold and L3 β fit (M5); the bootstrap block length (M7); the clustering threshold for stage D (M8).
- The report renderer change (one JSON → app and HTML export, replacing matplotlib `report.html`).
- Size gene: stays out until the tests in §9.7 justify it.
- Whether to add any further input; it must exist 2005–2026, be point-in-time and keyless. Keep the count at 25 unless I agree to a swap.
- **ORFE track (§20):**
  - battery parameters (power, energy, degradation cost; round-trip efficiency decided in round 28: 82 %);
  - the CVaR level α and the risk-aversion λ defaults;
  - whether a better tail estimator (O5) should replace the trailing empirical p99 in the sizing rule (a change to a decided design point);
  - whether the optimization bidder and the CVaR portfolio become candidates for `current_bot.json`, or stay benchmarks only;
  - solver choices.

### 17.3 Round 18–19 choices: decided in round 20
I said "NOW is the time to fix any of the previous decisions", so Claude decided these under delegation. Each is reversible; the reasons are in `docs/design_rationale.md`.

| # | Question | Decision |
|---|---|---|
| R19-1 | How profit affects offspring (§11.2) | rank-weighted selection, pressure 0.5; uniform and ε-lexicase compared in O8 |
| R19-2 | Market-time Life mode (§11.3) | added as M6b |
| R19-3 | Starting population (§9.5) | mixed 90 % random (PTC2) / 10 % founders, plus a no-founder control |
| R19-4 | Exact "out of money" (§10.1) | (a) can't post collateral for the smallest bid; (c) "MISO-eligible" offered as a preset |
| R19-5 | Futures as inputs (§6.4) | kept out: no keyless 2005–2026 source |
| R19-6 | Documenting local variables (§14.2) | full-word names + comments |
| R19-7 | Visual reference (§14.5) | supplied by me in round 20 |
| D1 (r18) | Decision time | 10:30 EPT on D−1 for every year |
| D2 (r18) | Sunday NERC holiday | flag the Sunday and the following Monday (confirmed by me in round 28) |
| D3 (r18) | Fees before the Rates Factors file | build with labelled placeholder rates |

Still needed from me: **R1**, MISO's *Market Settlements Rates Factors* file (Cloudflare blocks scripts; I download it in a browser and attach it; decided round 28). Until then fees and RSG are labelled estimates and the MPD is the $12 floor, labelled "estimate".

---

## 18. Do not
- Don't read, score on, or print anything from the hold-out outside `final-test`.
- Don't use `CALIBRATION_ONLY_*` constants inside simulation code.
- Don't let any feature read data except through `visible()`.
- Don't refer to locations by name inside bots.
- Don't feed GPR, oil, global gas, planned projects, ASOS actuals, MISO load forecasts or the event calendar to bots. They are reporting only.
- Don't use a language model to read news for bots.
- Don't add data sources that need keys or registration without asking me.
- Don't put formulas in JavaScript; the UI displays what Python computed.
- Don't load CDN assets, fonts or telemetry.
- Don't download more than about 1 GB without telling me first.
- Don't change a decided design point silently. Propose, ask, then log it.
- Don't fabricate citations, numbers or URLs. Mark [verify] instead.
- Don't use a commercial or licence-keyed solver (Gurobi, CPLEX, Mosek, Knitro). Everything must run offline with open-source solvers (§20.2).
- Don't let an optimization model see more than a bot would. Scenario sets, forecasts and fitted parameters all come through `visible()`; perfect-foresight models are labelled "upper bound, not a strategy".
- Don't compare methods on different windows, costs or trial counts. The leaderboard (§20.11) uses one protocol for everything.
- Don't let a trader's generated source code and the engine disagree; the equivalence test is the referee (§9.1).
- Don't present a value computed from market data or from the trader's account as an editable setting (§13.1).
- Don't call a trader "best" on in-sample profit (§11.4).
- Don't let a refine run hide that its lineage's sealed test was already opened (§11.5).
- Don't put grey backgrounds or grey surfaces in the UI, and don't draw boxes around buttons: actions are clickable words (§14.5).
- Don't use a language model to write or mutate traders' code (hindsight leak, §9.1).
- Don't compare a child's fitness with an elite's fitness from a different window (§11).
- Don't commit without a row in `docs/change_ledger.md` (§14.2).

---

## 19. Glossary seed (start `docs/glossary.md` with these)

| Term | Meaning |
|---|---|
| ISO | Independent System Operator; runs the grid and the electricity markets (MISO, CAISO, PJM, NYISO, ERCOT, ISO-NE) |
| DA / RT | day-ahead and real-time markets |
| LMP | locational marginal price, $/MWh, at one location and hour; components energy, congestion (MCC) and loss (MLC) |
| hub | a trading hub: a liquid average of many nodes (8 in MISO today) |
| operating day | the day D the power flows; bids are placed on D−1 |
| hub-hour / location-hour | one hour at one hub or location: the unit a bid is placed on |
| virtual bid, INC, DEC | financial position in DA, reversed in RT; INC = virtual supply, earns DA − RT; DEC = virtual demand, earns RT − DA |
| spread | DA − RT |
| cleared | the bid's limit price was met, so it was accepted in DA |
| RSG | Revenue Sufficiency Guarantee: an uplift cost allocated partly to virtuals |
| MPD, VMEW | MISO credit terms: price-difference value ($/MWh, ≥ $12) and a 2-day exposure window |
| ruin floor | the equity at which a career ends |
| career | the rules under which a bot stops trading (L1–L5) |
| elite, niche | the best bot in one cell of the MAP-Elites map, and that cell |
| hold-out | the sealed 12 months, scored once per run |
| (obs.) / [verify] | observed in this project / not yet checked |
| VaR, CVaR / expected shortfall | the loss exceeded with probability 1 − α, and the average loss beyond it |
| SAA | sample average approximation: replace an expectation by an average over sampled scenarios, then optimize |
| perfect-foresight bound | the profit an optimizer earns knowing future prices; an upper bound, never a strategy |
| policy | a rule mapping what is known now to a decision |
| state of charge (SoC) | energy stored in a battery, MWh |
| shadow price / dual | how much the optimal objective changes per unit relaxation of a constraint; an LMP is the shadow price of power balance at a location |
| DC-OPF | DC optimal power flow: the linearised grid-dispatch problem whose duals give LMPs |
| ARL | average run length: expected time before a sequential test (e.g. CUSUM) raises an alarm |
| Pareto front | the set of solutions no other solution beats on every objective |
| trader (bot) | one evolved strategy: genome + generated source code + life (§9.1) |
| genome | the trader's slot trees and numeric genes; what evolution changes |
| founder | a hand-written starting trader with a stated reason (§9.5) |
| lineage, generation | a trader's ancestors and descendants; generation = lineage depth (§9.4) |
| selection pressure | how strongly fitness raises a trader's share of offspring (§11.2) |
| out of money | can't post collateral for the smallest bid: the default death (§10.1) |
| capital floor / drawdown limit | stop at a wealth level / stop after a fall from the peak (§10.1) |
| best bot | highest out-of-sample fitness among traders passing the deployment gates (§11.4) |
| Life mode | the market-time ecology: traders live, reproduce and die day by day through history (§11.3) |

---

## 20. The ORFE track (added 2026-10-23)

### 20.1 Why, and the one rule every module follows
I'm applying to study Operations Research and Financial Engineering (ORFE), and this project is my portfolio piece. Evolution and MAP-Elites are closer to computer science than to OR. So the project also gets a set of **formal optimization, stochastic-modelling, risk and statistics modules**. They use the same data, simulator and report card as the evolved bots, and they are **compared head-to-head with them**.

The centrepiece question becomes: **"What does an optimizer find, what does evolution find, and why do they differ?"**

Every ORFE module must:
1. **State its model formally** in `docs/maths.md`: decision variables, objective, constraints, information available at decision time. Include a worked numeric example, the function that implements it, and the test that checks it (same three-way link as §14.2).
2. **Use only point-in-time information.** Scenarios, forecasts and fitted parameters are built from `visible()` data. Perfect-foresight models are allowed only as labelled **upper bounds**.
3. **Be solved with open-source, offline solvers** (§20.2).
4. **Settle through the same simulator** (M3): same clearing rule, fees, RSG, caps, sizing rule, career model and hold-out rules.
5. **Appear on the methods leaderboard** (§20.11) under the same protocol as everything else.
6. **Meet the engineering standards** (§14): naming, docstrings, offline tests, benchmarks, an app page, docs.

### 20.2 Solvers and libraries
Use open-source tools only. Before adding each, check its licence and record it in `docs/dependencies.md`:
- **LP and MILP:** HiGHS, through `scipy.optimize.linprog` / `milp` or `highspy`.
- **Convex models** (CVaR, quadratic programs, log-utility): `cvxpy` with Clarabel (handles exponential cones for log-growth), OSQP or SCS.
- **Statistics:** `scipy.stats` (e.g. `genpareto` for extreme-value fits), `statsmodels` (quantile regression, Markov switching, Cox models if suitable). `arch` for GARCH only if its licence fits.
- **Prefer your own short implementations** for the algorithms being showcased (NSGA-II, CUSUM, Shiryaev–Roberts, successive halving, the dynamic-programming solvers). Check them against a library in a test where one exists, the same "readable reference plus check" rule as §14.3.
- **No commercial or licence-keyed solvers** (§18).

### 20.3 O0: Why prices differ by location (DC optimal power flow)
An explanatory module, so the report shows where LMPs come from.
- **Model:** a 3-bus (then 5-bus) network with generator costs, loads and one line limit. Solve the DC-OPF linear program: minimise generation cost subject to power balance at each bus, line flows from a PTDF (power transfer distribution factor) matrix, and line limits.
- **Show:**
  - the LMP at each bus is the **dual (shadow price)** of its balance constraint;
  - when the line limit binds, LMPs separate, and the difference is the congestion component (MISO's MCC);
  - losses (MLC) are left out of the DC model, and the doc says so.
- **Link to the project:** connect this to the `congestion_share_28d` feature and to why virtual spreads are larger at congested nodes.
- **Done when:** the duals match a hand-derived answer in a test, and `docs/explanations/lmp_from_opf.md` walks through it with figures.
- **Timing:** with M0 (docs only, no data needed).

### 20.4 O1: Stochastic price models and scenario generation
One scenario generator, used by the synthetic tests (M4), the G1 stress paths (M7), the optimization bidder (O2) and the battery policies (O4).
- **Models for the hub spread s = DA − RT and for the (DA, RT) pair**, each fitted on visible data only and refitted on a rolling schedule:
  1. **Stationary block bootstrap** of historical days, the model-free baseline. Choose the block length with a documented rule.
  2. **Regime-switching model:** a hidden Markov chain with calm and stress regimes and heavy-tailed (Student-t) emissions, fitted by EM.
  3. **Mean-reverting jump model** for price levels: Ornstein–Uhlenbeck plus compound-Poisson jumps, with seasonality in hour and month. Use levels, not logs, because MISO prices go negative.
  4. **Conditional (analogue) scenarios:** the K most similar past days by visible features (weather forecast, gas, season), or quantile regression of the spread on features.
- **Validation:**
  - compare simulated against real spreads on mean, variance, tail quantiles (p99, p99.9), excess kurtosis, autocorrelation, cross-hub correlation and the frequency of spike days;
  - score forecasts with proper scoring rules (CRPS, pinball loss) and probability-integral-transform histograms;
  - use rolling-origin evaluation only.
- **Stress scenarios:** replay the worst real days (Uri, Elliott, the 2014 polar vortex (2014-01-06 → 07 in our data: hub mean RT $189.9/MWh on the 7th, peak $1,966; obs. round 27)) scaled up, and sample from the stress regime. These test survival, and the report says so.
- **Done when:** each model has a validation table against real data, the generator is seeded and deterministic, and the look-ahead test covers every fitted parameter.

### 20.5 O2: An optimization-based virtual bidder (the main benchmark for evolution)
A bidder built by solving a stochastic program each day, instead of evolving a formula.
- **Decision (day D, made at the DA deadline on D−1):** MW at each hub-hour, split into DEC quantity q⁺ ≥ 0 and INC quantity q⁻ ≥ 0, optionally at several limit prices.
- **Scenarios:** K joint (DA, RT) scenarios for day D from O1, built from data visible at D−6 or earlier.
- **Base model (sample average approximation, mean-CVaR, a linear program via Rockafellar & Uryasev 2000, *J. Risk* 2(3), doi 10.21314/JOR.2000.038):**
  - profit in scenario k: π_k = Σ_{n,h} (q⁺ − q⁻)·(RT − DA)_k − fee·(q⁺ + q⁻)
  - maximise (1/K) Σ_k π_k − λ·CVaR_α(−π)
  - CVaR written as ζ + 1/((1−α)K) Σ_k u_k, with u_k ≥ −π_k − ζ and u_k ≥ 0
  - subject to: 0 ≤ q⁺, q⁻ ≤ cap(n); total MW per day ≤ the risk-budget limit; optionally CVaR ≤ daily_risk_budget × equity as a hard constraint.
- **Bid-curve extension:** offer quantities at a fixed grid of limit prices b_j. Whether a block clears in scenario k is a known 0/1 number given that scenario's DA price, so the model stays a linear program, and the bidder chooses its own clearing rate.
- **Second benchmark from the literature:** implement the online bidding algorithm of arXiv 1802.03010 (Baltaoglu, Tong & Zhao) as described in the paper. Read the paper first; don't reconstruct it from memory.
- **Variants to report:**
  - risk-neutral (λ = 0);
  - several λ values, tracing an efficient frontier of mean vs CVaR;
  - scenarios from each O1 model;
  - doubled costs.
- **Comparison with evolution:** report on the same windows (§20.11). Also add the optimizer as a **seed** for MAP-Elites (its daily decisions summarised as a bot whose "score" slot is the optimizer's expected spread) and as a **niche reference** on the heatmap.
- **Done when:**
  - the LP matches a brute-force answer on small cases;
  - point-in-time is tested;
  - the backtest runs through the M3 simulator;
  - the frontier and leaderboard rows exist.
- **Timing:** after M3 and O1.

### 20.6 O3: A CVaR portfolio of elites
Instead of deploying one bot, choose weights over the archive's elites.
- **Data:** a T × m matrix of daily P&L at unit weight for the m elites on the training window. Positions are kept so netting can be modelled.
- **Models:**
  - **mean-CVaR linear program** (main);
  - mean-variance (a quadratic program);
  - **growth-optimal** (maximise Σ_t log(1 + r_t·w), a convex exponential-cone program), plus fractional Kelly;
  - risk parity;
  - equal weight, and the best single elite (baselines).
- **Constraints:**
  - w ≥ 0;
  - |Σ_i w_i·q_i(n,h,t)| ≤ cap(n) for every hub-hour in the window (the combined net position respects the liquidity cap; linear);
  - fees charged on the **net** position, since one trader nets its own bids (settled in round 18: admin fees and DA RSG on the net position per node-hour; RT RSG on net virtual supply summed over nodes; `market_rules.md` §3.2);
  - the daily risk budget.
- **Protocol:**
  - rolling re-optimisation (e.g. monthly) and walk-forward out-of-sample evaluation;
  - weight shrinkage or turnover penalties as documented options;
  - the portfolio counts as one more selection step in the deflated-Sharpe trial count.
- **Report:** weights over time, the frontier, diversification benefit vs the best single elite, and how much netting saves in fees.
- **Done when:** LP and QP answers match on small cases, the portfolio is evaluated out-of-sample through the simulator, and it appears on the leaderboard.
- **Timing:** after M6.

### 20.7 O4: Battery storage arbitrage (sequential decisions under uncertainty)
A second, physical decision problem on the same price data: a small battery buying low and selling high.
- **Label it as a study, not a deployable strategy.** A real battery is a physical resource that needs MISO registration and interconnection.
- **Parameters** (configurable `[battery]` table; defaults are an open decision §17.2):
  - power P MW and energy E MWh (e.g. 5 MW / 20 MWh, small enough to be a price-taker under the same cap logic);
  - charge and discharge efficiencies η_c, η_d (EIA, Today in Energy 2021-02-12: the US battery fleet averaged a monthly round-trip efficiency of 82 % in 2019; **default 82 %**, decided round 28);
  - degradation cost κ $/MWh throughput;
  - start-of-day and end-of-day state of charge.
- **Dynamics:** e_{t+1} = e_t + η_c·c_t − d_t/η_d, with 0 ≤ e_t ≤ E and 0 ≤ c_t, d_t ≤ P. Revenue Σ p_t·(d_t − c_t) − κ·(c_t + d_t).
- **Simultaneous charge and discharge:** with negative prices an LP may charge and discharge at once to waste energy. Either forbid it with a binary (a MILP) or show it is unprofitable under the parameters. Test both.
- **Policies, from simplest to most advanced** (organised by a policy-class framework, Powell's four policy classes: Powell 2019, *EJOR* 275(3), doi 10.1016/j.ejor.2018.07.014):
  1. **Perfect-foresight LP:** the upper bound, never a strategy.
  2. **Deterministic look-ahead / rolling intrinsic:** re-solve each day using a point forecast of tomorrow's prices.
  3. **Stochastic dynamic programming:** a value function over a state-of-charge grid, with prices from the O1 regime model (backward induction).
  4. **Approximate DP / policy-function approximation:** a parameterised policy (e.g. charge below price θ₁, discharge above θ₂, depending on SoC) tuned by simulation optimisation.
  5. **Evolved policy:** the GP engine evolves the battery's decision rule, using the same feature catalogue.
- **Two settlements:** schedule in DA at D−1, then adjust in RT, with the deviation settled at the RT price. State exactly what is known at each RT decision (e.g. RT prices up to hour h−1) and test it.
- **Report:** profit as a share of the perfect-foresight bound for each policy, by year and season; behaviour around Uri and Elliott; sensitivity to efficiency and degradation cost.
- **Done when:**
  - the LP matches a hand-solved 3-hour example;
  - the dynamic program agrees with brute force on a tiny grid;
  - every policy runs point-in-time;
  - the bound-ratio table exists.
- **Timing:** after M3 and O1.

### 20.8 O5: Risk measurement and VaR backtesting
The sizing rule uses an empirical trailing p99 that was exceeded on **2.2 % of days instead of 1 %** (§13). Treat this as a formal risk-model problem.
- **Estimators of the 1-in-100-day loss and of expected shortfall,** all point-in-time:
  - trailing empirical quantile (current);
  - **extreme value theory:** peaks-over-threshold with a generalised Pareto tail; document the threshold choice and show a mean-excess plot;
  - GARCH-filtered historical simulation;
  - Cornish–Fisher;
  - a regime-conditional estimate from O1.
- **Backtests:**
  - Kupiec's proportion-of-failures test;
  - Christoffersen's independence and conditional-coverage tests (breaches cluster in volatile years such as 2022);
  - the expected-shortfall backtests of Acerbi & Székely (MSCI, December 2014; three model-independent tests).
  - Report p-values by period, 2015–2025.
- **Consequence:** if an estimator passes where the current one fails, **propose** switching the sizing rule to it, with the effect on storm-day losses and fitness. Don't switch silently; it is a decided design point (§17.2).
- **Done when:** every estimator is look-ahead-tested, the backtest table exists, and the Risk app page shows the estimators side by side.
- **Timing:** after M3 (needs benchmark P&L), or earlier on the calibration sample.

### 20.9 O6: Sequential analysis, optimal stopping and survival statistics (the career model, done rigorously)
- **CUSUM calibration** (L4):
  - choose the threshold from a target **average run length** under "edge still present" (false-retirement rate), and report the detection delay when the edge vanishes;
  - compute ARLs by simulation and check them against Siegmund's approximation (Siegmund 1985, *Sequential Analysis*, Springer);
  - compare with **Shiryaev–Roberts** (Roberts 1966, *Technometrics*, doi 10.1080/00401706.1966.10490374) and Bayesian online change-point detection (Adams & MacKay 2007, arXiv 0710.3742).
- **Quitting as optimal stopping:** a Bayesian trader with a prior on their edge updates it from monthly P&L and quits when the value of continuing falls below the outside option (T-bills minus fixed costs). Solve the stopping problem by dynamic programming, and compare its decisions with the CUSUM rule and with the calibrated L3 hazard.
- **L3 calibration as an estimation problem:**
  - fit β by the **method of simulated moments**, matching the 1-, 2- and 3-year survival points (44 / 24 / 15 %);
  - report standard errors (bootstrap) and identification problems: three moments for five parameters means some β are fixed by assumption, and the doc must say which.
- **Survival analysis of the archive:**
  - Kaplan–Meier curves of bot careers by niche;
  - a **Cox proportional-hazards model** of which bot traits (selectivity, net direction, formula size, features read) predict death;
  - test the proportional-hazards assumption.
- **Done when:** ARL tables, the stopping-rule comparison, the moment fit with standard errors and the survival figures exist, each with tests on simulated data with known answers.
- **Timing:** with M5.

### 20.10 Order and dependencies

| Module | Starts after | Main milestone it attaches to |
|---|---|---|
| O0 DC-OPF explanation | nothing | M0 |
| O9 price impact (§20.12) | M1 (cleared-bids data) | M1–M2 |
| O1 scenario generation | M1, M2 | M2–M3 |
| O5 risk measurement | M3 (earlier on the calibration sample) | M3 |
| O2 optimization bidder | M3, O1 | M3–M4 |
| O4 battery | M3, O1 | M4–M5 |
| O6 sequential analysis and survival | M5 | M5 |
| O3 CVaR portfolio | M6 | M6–M7 |
| O7 inference upgrades (§20.11) | M7 | M7 |
| O8 search as OR (§20.11) | M6 | M6–M8 |
| O-write-up (§20.13) | O2, O3, O4, M7 | M9 |

Design M1–M3 interfaces with these in mind:
- `visible()` must serve fitted models and scenario sets;
- the simulator must accept a **decision matrix** (MW per hub-hour per day) from any source, not only from a bot;
- the report card must take any strategy's daily P&L.

### 20.11 O7 and O8: inference and search, plus the methods leaderboard

**O7. Inference upgrades** (with M7):
- Next to the deflated Sharpe ratio, add:
  - **White's Reality Check** and **Hansen's SPA test** against the do-nothing benchmark;
  - **Romano–Wolf step-down** for multiple strategies;
  - the **model confidence set** for the leaderboard (Hansen, Lunde & Nason 2011, *Econometrica* 79(2), doi 10.3982/ECTA5771).
- **Bootstrap confidence intervals** on every strategy's F.
- **Power analysis:** the smallest annual edge (in $/MWh and in Sharpe) that 20.5 years of walk-forward data could detect at 5 % significance, given the measured trial count. This says how much a "no edge" result actually means.

**O8. Search treated as an OR problem** (after M6):
- **Evaluation budget allocation:**
  - successive halving / Hyperband racing as the multi-fidelity option;
  - **optimal computing budget allocation (OCBA)** (Chen, Lin, Yücesan & Chick 2000, *Discrete Event Dyn. Syst.* 10, doi 10.1023/A:1008349927281) for deciding which noisy elites to re-evaluate.
  - Measure the speed-up against plain MAP-Elites at equal quality.
- **Multi-objective comparison:** your own **NSGA-II** over (log-growth, maximum drawdown, CVaR) vs MAP-Elites, under an equal evaluation budget and several seeds. Compare hypervolume, QD score, archive coverage and the best out-of-sample F.
- **CMA-ES / CMA-MAE** on continuous constants as an emitter (already listed as optional in §11).

**The methods leaderboard** (report card and app page), one protocol for all:
- the same walk-forward windows, costs (and doubled costs), point-in-time data, career model and gates G1–G7;
- **trial counts tracked per strategy class**, so the deflated Sharpe is fair to each;
- strategy classes:
  - the baselines;
  - the best evolved elite;
  - the evolved portfolio (O3);
  - the optimization bidder at each λ (O2);
  - the online bidder from 1802.03010;
  - the battery policies (O4) on their own leaderboard tab, as a separate problem;
- **one hold-out opening per finished run** scores every class's chosen strategy together (G8), logged as usual.

### 20.12 O9: Price impact and the price-taker assumption
The design assumes our bids don't move prices and enforces it with the 5 MW cap. Test that assumption with data.
- **Data:** the cleared-bids reports (2023+) with the hub attribution method from `capital_sizing.md` §2 (observable hub-hours only, 25–48 %).
- **Estimate:**
  - how the hub's DA − RT spread relates to net cleared virtual MW (virtuals are supposed to push DA toward RT);
  - a linear impact coefficient λ ($/MWh per MW), with confidence intervals.
- **Caveats** (state them): endogeneity (traders bid more when they expect a spread), and selection into observable hours. Propose an identification strategy before claiming causality, and mark the result as associational otherwise.
- **Use:** report what spread change 5 MW would cause under the estimate, and add an **optional linear impact** to the simulator as a sensitivity run. Price-taking stays the default.
- **Done when:** the estimate, its intervals, the caveats and the sensitivity run are in `docs/explanations/price_impact.md`.

### 20.13 Write-up deliverables (for my application and portfolio)
- **`docs/orfe_report/report.md`:** a paper-style write-up.
  - Sections: problem, market rules, data and point-in-time design, models (evolution and each O-module, formally), experimental protocol, results (leaderboard, frontiers, battery bound ratios, risk backtests, survival), limitations, and what an honest "no edge" would mean.
  - Every number links to the script that produced it; every citation is verified or marked [verify].
  - If an offline LaTeX toolchain is available, also produce a PDF; otherwise Markdown rendered with KaTeX in the app.
- **`docs/orfe_report/summary.md`:** a two-page plain-English summary I can attach or link: question, approach, key figures, honest results.
- **A methods map table:** each module against the ORFE area it demonstrates (optimization, stochastic processes and probability, statistics and inference, financial mathematics and risk, computation and algorithms), with the file that implements it.
- **Figures** (generated by scripts in `tools/`, reproducible):
  - the MAP-Elites heatmap with optimizer reference points;
  - the mean-CVaR frontier;
  - the portfolio weights over time;
  - battery SoC on a storm day with the perfect-foresight path;
  - VaR breach timelines;
  - Kaplan–Meier curves;
  - NSGA-II vs MAP-Elites fronts.
- **Write the report as results arrive,** one section per finished O-module, and show me each section when it's drafted.
