# Round 19: review of the briefing (20 questions)

Date: 2026-10-23. Areeb asked for the original briefing (`CLAUDE.md`) to be reviewed and revised around 20 questions. For each question this doc gives:
- **Today:** what the briefing and the repository actually say or contain;
- **Revision:** what changed in `CLAUDE.md`, with the section;
- **Decision:** what still needs Areeb's choice, if anything.

Two kinds of change:
- **Areeb's directives**, now decided: out-of-money death by default (Q12); buttons for code, best bot and the sealed test (Q1, Q13, Q15); UI separation (Q18); a change ledger and complete documentation (Q19); the visual style (Q20).
- **Design choices** with options and a recommendation: listed in §21 and in `CLAUDE.md` §17.3.

Honest baseline: **no data has been imported, and none of the engine has been written in this repository.** The 40-test capital slice is still missing (rounds 17–18). Every "today" below describes the *design*, not working software.

Citations: the bibliographic details (authors, title, venue, year, DOI or arXiv ID) of every source cited here were checked on 2026-10-23 against the arXiv API or Crossref (obs.; §22). What I say each paper *contains* is from memory unless stated, and is marked [verify] where it matters.

---

## Q1. What makes each trader an organism? Its own code, viewable with a button?

**Today.** A bot is a fixed skeleton of slots (`where`, `when`, `score`, `side`, `price`, `size`, `risk`) filled with typed expression trees and numbers, saved as JSON (`CLAUDE.md` §9). Executable single-file code exists only as a later export (`export-bot`, M9, §14.6). There is no "view code" button.

**Revision (§9.1).** A trader has three parts:
- a **genome**: its trees and numeric genes, as canonical JSON;
- its **source code**: a standalone, standard-library Python module generated from the genome as soon as the trader is born, `trader_<id>.py`. This is the literal executable code. Running it on a day's inputs prints that day's bids;
- a **life**: its account, trades, equity curve and, if it died, the cause and date.

The fast engine (NumPy/Numba) must give exactly the same bids as the generated file; an equivalence test checks this on random days (moved from M9 to M4). Every trader page gets a **View code** button (syntax-highlighted, with Download).

Why evolution edits the genome tree rather than the text: a random edit to Python text almost always gives a program that doesn't run. Editing typed syntax trees guarantees every child is a valid, well-typed program (strongly typed GP; Montana 1995). The code is generated from the tree, so code and tree are always the same organism.

## Q2. What code do traders start with, and why?

**Today.** "Seed with N random bots" (§11). No founders, no reason given.

**Revision (§9.5).** Recommended: **mixed founders**, about 90 % random typed trees and 10 % named founder strategies.
- **Random trees** use ramped half-and-half: trees of mixed depths, some full and some sparse. It is the standard GP initialisation [verify: Koza 1992].
- **Founders** are hand-written, each tagged with a reason:

| Founder | Rule | Why it was chosen |
|---|---|---|
| `always_inc` | INC at every hub-hour | mean DA − RT is slightly positive at every hub (Claude Science, obs.); a DA premium persists in MISO (Birge et al. 2017, read in round 18, obs.) |
| `always_dec` | DEC at every hub-hour | the mirror: profits in RT price spikes (Uri) |
| `persistence` | repeat the sign of the last visible spread | baseline in §12.1 |
| `premium_follow` | side = sign of `spread_mean_28d` | bets the recent average premium continues |
| `premium_fade` | the opposite | bets it reverses |
| `heat_dec` | DEC on high `cdd_fcst` afternoons | hypothesis: hot days surprise RT upward [unverified] |
| `wind_inc` | INC when `wind_fcst × wind_cap_region` is high | hypothesis: windy days push RT down [unverified] |

The lineage view shows whether the winners descend from a founder or from a random tree. That tells you whether human ideas helped. Option: random only, or founders only (§21, R19-3).

## Q3. How are traders identified, named and searched?

**Today.** Bots are named like "7c2e" (§9.1), with no rule. There is no search and no lineage record.

**Revision (§9.4).**
- **Id:** the first 8 hex characters of the SHA-256 of the canonical genome JSON, so identical code gets the identical id. The full hash is stored, and collisions are checked.
- **Name:** a two-word name generated deterministically from the id, e.g. `7c2e9a41 amber-heron`. It is for humans; the id is authoritative.
- **Birth record:** run, evaluation number, generation (lineage depth), parents, the operator that made it, the random seed used, its niche, fitness and death cause/date. Stored in `runs/<run>/lineage.sqlite`.
- **Storage:** every evaluated trader gets a row (about 200 bytes). Full genomes are stored for every trader that ever entered the archive and all its ancestors. Any other trader can be **regenerated exactly** from parents + operator + seed, because the run is deterministic.
- **Traders page:** search by id prefix, name, feature used, founder, niche, generation, alive/dead and fitness range. Each **Trader page** shows code, tree, parents (clickable), a descendants tree, and the family's improvement history.

## Q4. How does mutation work, and what supports it?

**Today.** Three lines in §9.2: subtree crossover and mutation, Gaussian constants, categorical set mutation.

**Revision (§9.6).** What can change, and how:

| Part | Operator | Randomness |
|---|---|---|
| tree structure (`where`, `when`, `score`) | **subtree mutation**: replace a random subtree with a new random well-typed one | node chosen at random; new subtree from ramped half-and-half |
| tree nodes | **point mutation**: swap a node for one of the same type and arity (`>`↔`<`, `+`↔`−`, a feature for another with the same unit) | uniform over allowed swaps |
| tree size | **hoist / shrink**: replace a subtree by one of its own subtrees, removing code | controls bloat (Luke & Panait 2006 compare bloat-control methods) |
| two parents | **subtree crossover** between the same slot of two parents, types matched | Montana 1995 (typed); Koza 1992 [verify] |
| constants in trees | **Gaussian**: σ = 10 % of the feature's historical inter-quantile range (proposal), clipped to the range | |
| category sets (`loc_type in {…}`) | add or remove one member | |
| numeric genes (side thresholds, price offset, size scale, risk settings) | Gaussian within bounds; optional **iso+line-DD**, which steps along the line between two elites (Vassiliades & Mouret 2018, arXiv 1804.03906) | |
| (later) all continuous genes | **CMA-ME** emitter (Fontaine, Togelius, Nikolaidis & Hoover 2019, arXiv 1912.02400) | |

**Never mutated:** the hard caps (MW cap, the out-of-money rule, data visibility), the skeleton shape and the unit/type system.

**How random:** every draw comes from a seeded generator (NumPy PCG64), one stream per worker, and the seed is recorded with the child. So a mutation is random but exactly reproducible. Operator probabilities are a config table; the proposed defaults are subtree 0.25, point 0.20, constant 0.30, hoist 0.10, crossover 0.15. They are tuned in M6 and the result is documented.

## Q5. What kind of reproduction? How does profit affect offspring?

**Today.** Plain MAP-Elites (Mouret & Clune 2015, arXiv 1504.04909): parents are picked **uniformly at random** from the archive's elites, and a child takes a cell only if it beats the incumbent. Profit affects reproduction only through being an elite or not. A trader with ten times the profit of another elite gets **no more offspring**. Reproduction happens in batches, continuously, while the run lasts.

**Revision (§11.2).** Options (R19-1):
- **A** uniform (standard MAP-Elites; maximum diversity);
- **B (recommended)** rank-weighted: P(elite i is a parent) ∝ (1 − p) · uniform + p · rank-based weight, with a **selection-pressure** knob p ∈ [0, 1], where p = 0 is plain MAP-Elites. Proposed default 0.5. More profitable traders then get more offspring, and the UI shows each trader's offspring count;
- **C** curiosity: favour elites whose children tend to enter the archive (one of the selection variants in Cully & Demiris 2017, arXiv 1708.09251 [verify details]);
- **D** wealth-driven reproduction in market time (Q6, Life mode).

O8 compares A and B at equal budget.

## Q6. Do traders evolve through market time? Why so fast? How many generations?

**Today.** Evolution runs in **compute time**, not market time. Each evaluation replays one trader over a rolling ~1-year window of history (plus the next period for walk-forward). The window steps through 2005–2025 as the run goes on. A single trader does not live through decades and does not reproduce mid-history.

**Why it's fast** (explanation; numbers are estimates until M3/M6 benchmarks):
- history is already recorded, so nothing waits for markets;
- traders are price-takers and don't interact, so each can be replayed independently and in parallel;
- a hub trader-year is 8 hubs × 24 hours × 365 days = 70,080 location-hours of simple arithmetic. Vectorised code does that in milliseconds.

The target of 100,000 trader-years per hour on 20 cores is about 28 per second.

**Generations.** MAP-Elites has no strict generations. The app will show two counts:
- **batches done:** at the target speed and about 1,000 children per batch on 1-year windows, about 100 batches per hour (estimate);
- **lineage depth:** the longest chain of ancestors, likely tens to low hundreds per hour (estimate; measured from M6).

**Revision (§11.3).** Both are explained in the app. Also proposed (R19-2): **Life mode**, a market-time ecology, as milestone M6b:
- a population lives through 2005-04 → 2025-09 day by day;
- each trader trades every day it is alive and dies when out of money;
- it **reproduces when its equity reaches k × its starting capital** (proposal k = 2), passing starting capital to a mutated child;
- a child trades only from the day after its birth, so its whole career is out-of-sample relative to its creation.

Generations are then limited by market time: a trader that doubles every 2–5 years gets 4–10 generations in 20 years (arithmetic, not measured). That is too few for search, but it is the literal natural selection Areeb described in round 1, and an honest realism check.

Related work:
- the Santa Fe artificial stock market (Arthur, Holland, LeBaron, Palmer & Tayler 1997) evolved trader populations in market time, though its traders interact and ours don't;
- Lo (2004), *The Adaptive Markets Hypothesis*, argues for viewing markets as evolutionary ecologies.

Recommendation: keep MAP-Elites as the search engine and add Life mode as a showcase and comparison.

## Q7. Has all the MISO data been imported? Coverage and gaps?

**Today.** **No.** Nothing has been imported into this repository (obs.: `data/` holds only the rule documents from round 18, which git ignores). Claude Science's calibration sample (8 hubs, 2019-01 → 2025-09) was not carried over.

On MISO's server (obs., rounds 17–18 probes; `CLAUDE.md` §7.3):
- DA and final RT prices are available from 2005-04 to 2026-10-19 in three file eras;
- cleared bids exist from 2023 only.

Known gaps and quirks:
- 2005 files have no value-type column, so no congestion or loss components;
- components are present "from at least 2010" [verify 2005–2009];
- 2015-02 is split between two file styles;
- the hub set changes over time (4 → 8);
- MISO may stop the public reports (access risk).

**Revision (§7.0).** A status table in the briefing. M1's build writes `docs/data_coverage.md` plus a coverage map on the Data page: source × month, with every missing day or file listed.

## Q8. What can a bot see? Futures? Past prices? How is the future kept out?

**Today.**
- **Past electricity prices:** yes. Features 1–7 come from DA prices visible at the deadline (including D−1's DA, published the afternoon before) and RT prices up to D−6.
- **Futures quotes or past futures prices:** **no.** They are deliberately excluded:
  - EIA's free gas futures series stopped on 2024-04-05;
  - exchange data for MISO power futures is not free [verify];
  - §7.1 requires every input to exist 2005–2026 from one keyless source.
- **Keeping the future out:** every data column carries an `available_at` time; `visible()` is the only way features read data; a look-ahead test perturbs everything at or after a decision time and checks no feature changes.

**Revision (§6.4, §8).**
- The decision time is stated: 10:30 EPT on D−1 for every year (pending round 18 D1).
- A **"What did it see?"** panel on the Trader page shows, for any chosen day, the exact input values the trader saw and the bids it made.
- Futures remain out unless Areeb supplies a source (R19-5).

## Q9. Which outside factors are included, and which are populated?

| Factor | Role | Populated in this repo? |
|---|---|---|
| Henry Hub gas spot → `gas_price`, `gas_chg_5d`, `gas_vol_20d` | bot input | no (seen in Claude Science, obs. there) |
| US Economic Policy Uncertainty → `epu` | bot input | no |
| Geopolitical risk (GPR) | **reporting only**, not a bot input (round 10) | no |
| NWS weather forecasts → 7 features | bot input | no |
| EIA-860M wind/solar capacity → 2 features | bot input | no |
| WTI oil, World Bank Pink Sheet | reporting only | no |

**Revision (§8).** The feature table gets a "populated" column that the build fills in. The Data page shows, per feature, its first and last day with data.

## Q10. Are trading costs grounded in evidence, and time-varying?

**Today.** Round 18 (`docs/market_rules.md` §3):
- **measured:** which charges apply and how they net (per node for admin and DA RSG; across nodes for RT RSG); the three RSG eras (none before 2008-11; high until 2011-03; lower after);
- **estimated:** the rates. Schedule 17 + 24 ≈ $0.090/MWh in October 2026 comes from search-index quotes; the RSG rate history is still missing (request R1 in round 18).

**Revision (§6.2).** Costs come from a **cost table by month (and hour for RSG)**, not a constant. Every rate is labelled "measured" or "estimate" in reports. G4 doubles everything. The $50k/year fixed cost stays labelled as an assumption.

## Q11. Which settings should users control?

**Today.** All `CapitalSettings` fields are presented as user inputs (§13). Some should not be:

| Setting | Today | Should be |
|---|---|---|
| `starting_capital_usd` | user | **your choice** |
| `daily_risk_budget` | user | **your choice** (how much risk per day) |
| `credit_share` | user | your choice; exact meaning to be checked in `capital.py` when it arrives [verify] |
| `mpd_usd_per_mwh` | user, default 12 | **from market data**: Attachment L's formula (50th-percentile DA−RT differential over the prior 12 months, reset each May 1, floor $12) |
| `max_mw_per_hub_hour` | user, 5.0 | the 5 MW and 5 % policy are **your choice**; the hub's median cleared MW is **from market data** |
| `ruin_floor_*` | user, default 2/3 | **optional**, off by default (Q12) |
| fees, RSG | constants | **from market data** (Q10) |
| risk-free rate | not specified | **from market data**: needs a keyless T-bill series [verify source; Fed H.15 was dropped in Claude Science] |
| collateral, Virtual MWh Limit | computed | **from the trader's account** (its bids) |
| trailing p99 loss | computed | **from the trader's account** |

**Revision (§13.1).** Every value gets one of three badges: **Your choice** (editable), **From market data** (read-only, with source), **From the trader's account** (read-only).

## Q12. What causes death? Make running out of money the default.

**Today.** Five layers (§10.1). The default death is equity at 2/3 of starting capital (a 33.3 % drawdown), plus an evolved personal loss limit, a quit hazard and CUSUM retirement.

**Revision (§10.1), Areeb's directive.** **Default death = out of money**: the trader can no longer post MISO's collateral for even the smallest bid (0.1 MW for one hour). In practice that means equity at or near zero. When equity is positive but too small for the bids a trader wants, the bids are **cut to what its credit allows** rather than killing it. All other layers become optional, off by default.

The two controls are different things:
- A **capital floor** is about the **level** of wealth: "below $X I may not, or should not, trade." Example: MISO's minimum capitalization ($500k tangible net worth for a non-FTR trader, `market_rules.md` §5.3). It ignores history.
- A **drawdown limit** is about the **path**: "stop after losing Y % from my peak." It is self-discipline relative to the high-water mark.

A trader that grew to $3M and falls to $2M has a 33 % drawdown. It trips a 30 % drawdown limit while still being far above a $1M floor.

Consequences, stated honestly:
- with proportional sizing, equity shrinks towards zero rather than through it, so out-of-money deaths come mainly from single storm days (Elliott cost 31.2 % at full size);
- far fewer traders will die than under the 2/3 floor;
- log-growth fitness already punishes deep drawdowns;
- `capital_sizing.md`'s headroom and "lowest $50k step" numbers were computed with the floor, so they become "under the optional floor preset";
- the existing tests may assume the 2/3 default. Step zero still runs the 40 tests as they are; the default changes afterwards, with test updates logged.

The exact out-of-money definition is R19-4.

## Q13. How do I find the best bot, and what does "best" mean?

**Today.** "The best bot that passes the gates" goes to `current_bot.json` (§11.1). There is no button and "best" is not spelled out.

**Revision (§11.4).**
- **Best** = the highest **out-of-sample** (walk-forward) fitness F among elites that pass the quick deployment gates (G1 survival, G2 skill vs trials, G4 doubled costs, G6 walk-forward); ties go to the smaller program. It is **not** the highest in-sample profit, which is usually the most overfitted trader.
- A **Best bot** button in the top bar of every page opens its Trader page, with a table of why it beat the next five.
- If none passes, the page says "Do nothing: no trader passes the gates", names the nearest candidate and the gate it failed.

## Q14. After a best bot emerges, can I refine it on the older data?

**Today.** Not described.

**Revision (§11.5).** A **Refine** button starts a new run seeded with the bot and mutants of it, on the evolution period 2005-04 → 2025-09 only. Options: stay in its niche, or open the whole map.
- Lineage continues across runs.
- The trial count carries over, so the deflated Sharpe counts every trial in the parent and child runs (refining is more searching, and the overfitting guard must know).
- **If the bot's sealed test has already been opened**, the refine run is labelled "hold-out already used": its sealed-test result can no longer count as clean. The only clean test left is forward data from 2026-09-22 on, which grows daily (the **Forward test** button).

## Q15. Where is the separate twelve-month test?

**Today.** G8 and `evobots final-test` (§7.2, §12.2); no UI.

**Revision (§12.4).**
- A **Final test (sealed 12 months)** button on the run's chosen trader. A confirmation explains it can be used once per run and is logged. The result page puts sealed-test metrics next to walk-forward metrics.
- **Separation** is enforced in five ways:
  1. the hold-out is a separate file under `data/holdout/`;
  2. only `final_test` knows its path;
  3. evolution workers get a data root without it;
  4. a test fails if any other module imports the hold-out reader or opens that path;
  5. every opening is logged (who, when, run, trader).
- The Home page shows the seal status ("never opened" / "opened on … for …").

## Q16. What does the grid map show?

**Revision (§11.6).** A plain explanation in the briefing and in the app:
- **horizontal axis:** net direction, from −1 (only INC: always selling in DA, betting DA > RT) to +1 (only DEC);
- **vertical axis:** selectivity, the share of available location-hours the trader bids on, log scale (0.1 % … 100 %);
- **each cell** holds the best surviving trader of that kind;
- **colour:** its fitness F on a colour-blind-safe sequential scale. A **blank (white) cell** means no surviving trader of that kind has been found yet;
- **click** opens the trader; **hover** shows name, F, profit and trades per day;
- a switch recolours by profit, maximum drawdown, lineage depth or founder origin.

What it tells you: how many different kinds of strategy survive, where the profitable ones sit (e.g. "selective INC traders"), and which kinds are empty.

## Q17. What do results and controls mean?

**Revision (§15.2).**
- Every metric and setting has a plain-English one-liner, unit, why it matters, a formula link (`maths.md`), and a "?" tooltip fed from `docs/glossary.md`.
- Each result page opens with a **"What happened"** paragraph written from templates by Python. It is deterministic, not a language model. Example of the form: "amber-heron made $412k over 2019–2024; 70 % came from INC bids at Indiana hub on summer afternoons; it died on 2022-12-23 (Winter Storm Elliott) when …"

## Q18. Can I change the interface myself?

**Today.** The architecture already separates browser page → `server.py` (routes) → `service.py` (bridge) → core (§15), with option A (HTML/CSS/JS, no build step) chosen in round 17.

**Revision (§14.5).**
- **Enforced** by an import test: `evobots.app` may import only `evobots.service`, and no core module may import `evobots.app`.
- Templates contain no formulas.
- `docs/how_to/change_the_ui.md` lists which file to edit for each kind of change.

## Q19. Is everything documented? A change ledger?

**Revision (§14.2).**
- **`docs/change_ledger.md`** (started this round): one row per change (date, round, commit, what, why, files, decision link). Updated with every commit; a test checks every round doc is listed.
- **Every** module, class and function (public and private) gets a docstring.
- **Every** constant gets a comment with meaning, unit and source.
- Every config key goes in `config_reference.md`; every library in `dependencies.md` (purpose, licence, version); every input and output file in `data_sources.md` / file-format reference; every dataclass field is documented.
- A generated **symbol index** (`docs/reference/`) lists everything with its purpose; a test fails when an item lacks documentation.
- **Local variables:** explained by full-word names (§14.1) plus comments where not obvious, rather than one doc entry each. A separate entry for every local would roughly double the code and drift out of date (R19-6).

## Q20. Does the UI follow the supplied visual reference?

**Today.** **No visual reference has been supplied.** Nothing is in the repository or in the messages so far. No UI exists yet (M1.5).

**Revision (§14.5).** Style rules now in the briefing:
- white page and card backgrounds; **no grey backgrounds or grey surfaces**;
- separation by whitespace and thin lines;
- a generous spacing scale and clear type sizes;
- one accent colour plus a colour-blind-safe data palette;
- a top navigation of at most seven items plus the Best bot button;
- every value lives in `theme.css` tokens.

The reference images should go in `docs/design/visual_reference/`; the tokens are then taken from them (R19-7).

---

## 21. Decisions needed (round 19)

| # | Question | Options | Recommendation |
|---|---|---|---|
| R19-1 | How profit affects offspring | A uniform MAP-Elites; **B** rank-weighted with pressure knob; C curiosity | **B**, default pressure 0.5, compared with A in O8 |
| R19-2 | Market-time Life mode | **add as M6b**; skip | **add** |
| R19-3 | Starting population | **mixed 90/10**; random only; founders only | **mixed** |
| R19-4 | Exact "out of money" | **(a)** can't post collateral for the smallest bid; (b) equity ≤ 0; (c) below MISO minimum capitalization | **(a)**; offer (c) as the "MISO-eligible" preset |
| R19-5 | Futures as inputs | **keep out**; find a source | **keep out** unless you have a keyless 2005–2026 source |
| R19-6 | Documenting local variables | **names + comments**; one doc entry per variable | **names + comments** |
| R19-7 | Visual reference | please add the images to `docs/design/visual_reference/` | – |

Still open from round 18: D1 decision time, D2 holiday rule, D3 placeholder fees, R1 the Rates Factors file.

## 22. Citations checked this round

Bibliographic data checked on 2026-10-23 via `export.arxiv.org/api/query` and `api.crossref.org/works` (obs.):

| Source | Identifier |
|---|---|
| Mouret & Clune (2015), *Illuminating search spaces by mapping elites* | arXiv 1504.04909 |
| Vassiliades & Mouret (2018), *Discovering the Elite Hypervolume by Leveraging Interspecies Correlation* | arXiv 1804.03906 |
| Cully & Demiris (2017), *Quality and Diversity Optimization: A Unifying Modular Framework* | arXiv 1708.09251 |
| Fontaine, Togelius, Nikolaidis & Hoover (2019), *Covariance Matrix Adaptation for the Rapid Illumination of Behavior Space* | arXiv 1912.02400 |
| Montana (1995), *Strongly Typed Genetic Programming*, Evolutionary Computation 3(2):199–230 | doi 10.1162/evco.1995.3.2.199 |
| Luke & Panait (2006), *A Comparison of Bloat Control Methods for Genetic Programming*, Evolutionary Computation 14(3):309–344 | doi 10.1162/evco.2006.14.3.309 |
| Lehman & Stanley (2011), *Abandoning Objectives: Evolution Through the Search for Novelty Alone*, Evolutionary Computation 19(2):189–223 | doi 10.1162/evco_a_00025 |
| Pugh, Soros & Stanley (2016), *Quality Diversity: A New Frontier for Evolutionary Computation*, Frontiers in Robotics and AI 3 | doi 10.3389/frobt.2016.00040 |
| Arthur, Holland, LeBaron, Palmer & Tayler (1997), *Asset Pricing Under Endogenous Expectations in an Artificial Stock Market* | doi 10.2139/ssrn.2252 |
| Lo (2004), *The Adaptive Markets Hypothesis*, Journal of Portfolio Management 30(5):15–29 | doi 10.3905/jpm.2004.442611 |

Not checked: Koza (1992), *Genetic Programming* (a book; [verify]).

## 23. Measured vs assumed

**Measured (obs.):** the repository contents (no data, no engine); the citation metadata above; the MISO facts carried over from round 18.

**Assumed or estimated:** evaluation speed, batches and lineage depth per hour (estimates until M3/M6 benchmarks); the Life-mode generation count (arithmetic on an assumed doubling time); the operator probabilities and the selection-pressure default (proposals); the founder hypotheses `heat_dec` and `wind_inc` (unverified ideas); futures-data availability.
