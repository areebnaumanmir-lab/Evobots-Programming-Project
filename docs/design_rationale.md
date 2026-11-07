# Design rationale: the logic behind every decision

A living write-up. Every design decision in evobots has an entry here: what was decided, why, what the literature says, what was rejected, and its status. **Update this file whenever a decision is made or changed.** The change ledger (`change_ledger.md`) records *when*; this file records *why*.

- Started in round 20 (2026-10-24). It covers:
  - the decisions of rounds 1–16 as recorded in the briefing (`docs/design_spec.md`);
  - rounds 17–19;
  - Areeb's 20 review questions (`rounds/round19_prompt_review.md`).
- The decision log for rounds 1–16 (`decisions_log.md`) arrived in round 21. Part C was rewritten from it (round 20 had reconstructed it from the briefing); the corrections are listed at the end of Part C.
- **Status labels:**
  - **kept:** reviewed in round 20 and still the best option;
  - **changed r20:** revised in round 20, reason given;
  - **delegated r20:** an open choice decided by Claude under Areeb's instruction "NOW is the time to fix any of the previous decisions", reversible;
  - **Areeb:** Areeb's own decision;
  - **open:** still needs Areeb.
- **Evidence markers:**
  - **(abstract)**: the claim is taken from the paper's abstract, retrieved and stored in `data/references_checked.json`;
  - **(memory) [verify]**: the paper's existence was checked, but the claim about its content is from memory;
  - **(obs.)**: measured in this project;
  - **(arith.)**: arithmetic shown in place.
- References are keyed as in [references.md](references.md). Every key there was checked against Crossref or arXiv by `tools/check_references.py`, or, where neither has a record, against a named primary record (round 27: a conference bibliography entry or the paper itself). Entries still marked "not found" are always cited with [verify]. Content claims below were checked against the abstracts or the papers in round 27; "(abstract)" or "(paper)" says which.

---

## Part A. The four questions on the trader itself (Q1–Q4), with the literature

### A1. What a trader is: representation and its own code (Q1)

**The question:** What makes each trader an organism? Does it have its own executable code you can open with a button?

**Options found in the literature:**

| Option | What it is | For | Against |
|---|---|---|---|
| **Typed tree GP** (Montana 1995) | programs as syntax trees; every function has argument and return types, and only well-typed trees are created | "enforces data-type constraints", avoiding "unnecessarily large search times and/or unnecessarily poor generalization" (montana1995, abstract); trees print directly as readable code | bloat (trees grow without gain); crossover can act like random macro-mutation (angeline1997, "Comparing subtree crossover with macromutation": the experiments "support the hypothesis that the building block hypothesis is not descriptive of the operation of subtree crossover", abstract) |
| **Grammar-guided GP** (whigham1995; survey mckay2010) | a grammar defines the language; trees are derivations of it | the whole trader language lives in one readable file; units are grammar categories | same search behaviour as typed GP; no extra benefit here beyond documentation |
| **Grammatical evolution** (oneill2001) | an integer string is mapped through a grammar into a program | simple genome | small genome changes can make large program changes: "many neighboring genotypes do not correspond to neighboring phenotypes" (rothlauf2006, abstract); harder to trace why a child differs |
| **Linear GP** (brameier2007) | a sequence of register instructions | fast to run | hard to read; much non-functional code |
| **Cartesian GP** (miller2000) | a fixed-size graph of nodes | reuses sub-expressions; neutral drift | hard to read as a rule |
| **PushGP** (spector2002) | stack-based programs with types, loops and self-modification | very general | far more power than a daily bid rule needs; hard to read |
| **Self-replicating machine code** (Tierra: ray1991; Avida: ofria2004) | each organism *is* executable code that copies itself and mutates | the literal "organism with its own code"; Avida is a platform for "self-replicating and evolving computer programs" (ofria2004, abstract) | built to study evolution, not to find good trading rules; most mutants don't work; unreadable |
| **Neural networks** (e.g. NEAT, stanley2002) | evolving network weights and topology | flexible | opaque. Rudin argues for "models that are interpretable in the first place" for high-stakes decisions (rudin2019, abstract). Rejected in round 9 for opacity and overfitting with ~20 years of data |
| **Language-model mutation of source code** (ELM: lehman2022; FunSearch: romeraparedes2024) | a language model proposes code edits; an evaluator keeps the good ones | edits the literal source; ELM with MAP-Elites produced "hundreds of thousands of functional examples of Python programs" (lehman2022, abstract) | **hindsight leak**: a language model has read about 2005–2026 markets and can steer rules toward known history, the same reason news-reading was rejected in round 9; needs the internet or a large local model (breaks offline, §14.4); not byte-reproducible (breaks the resume test, §11.1) |

**What GP trading studies report** (why readable, constrained rules and honest testing matter):
- Allen & Karjalainen (1999) evolved trading rules for the S&P index: positive excess returns after costs in one test period (1970–89), but "using data for other periods since 1929, the rules … do not lead to excess returns after transaction costs" (allen1999, abstract).
- Neely, Weller & Dittmar (1997, neely1997) found "strong evidence of economically significant out-of-sample excess returns" to GP rules for six exchange rates, 1981–1995 (working-paper abstract). Their 1999 intraday follow-up: "When realistic transaction costs and trading hours are taken into account, we find no evidence of excess returns" (Neely & Weller, 1999 draft, abstract; round 27), the same lesson as `paper_digest.md`: costs belong in the fitness.
- Bhattacharyya, Pictet & Zumbach (2002, bhattacharyya2002) built domain knowledge into GP for FX trading models (a symmetry property, a risk-adjusted fitness) and report "more robust performance" (Semantic Scholar summary of the abstract; the claim is about robustness, not out-of-sample profit).
- Chen & Navet (2007, chen2007) proposed testing GP traders against random-search baselines to tell an efficient market from an inefficient algorithm: if GP shows no ability "superior to a random search or a random trading behavior" there is no point investing further in it (Semantic Scholar summary). This supports the "random bots" baseline (§12.1).

**Decision (changed r20 in detail, kept in substance):**
1. **Typed tree GP with a fixed skeleton**, written as one **typed grammar file** (`bots/grammar.py`): the "trader language", readable on its own page. Types include units, so `spread + temperature` can't be written. Typed GP and grammar-guided GP give the same search here; the grammar form is chosen because it doubles as documentation.
2. **The organism's code:** each trader's genome is compiled into a standalone Python file the moment it is born. The **View code** button shows that file. The engine and the file must agree exactly, checked by a test.
3. **New in r20: the code can be read back.** The generated dialect is parsed back into a genome. You may edit a trader's file (or write one), and if it passes the grammar and unit checks it becomes a **founder** in a Refine run, labelled `founder:human`. Seeding GP populations is studied (langdon2000seeding: populations seeded with "perfect" programs still evolve towards general solutions, abstract).

**Rejected:** self-replicating machine code (not built for finding rules; unreadable); neural networks (opaque); language-model mutation (hindsight leak, not offline, not reproducible).

### A2. What traders start with (Q2)

**Options:**

| Option | For | Against |
|---|---|---|
| **Ramped half-and-half** (koza1992) | the classic mix of tree shapes | poor control over tree *size*; with a ~15-node limit many trees are cut or rejected |
| **PTC2** (luke2000ptc) | lets the user "request specific tree sizes" (luke2000ptc, abstract) | slightly more code |
| **Random only** | no human bias | wastes early evaluations; may never find simple, known strategies |
| **Seeded with known strategies** (langdon2000seeding; friedrich2015) | starts from sensible traders | seeds can take over the population and reduce diversity (burke2004 analyses diversity measures and their correlation with fitness; title and record checked); the benefit depends on the algorithm: "different optimization algorithms benefit very differently from seeding" (friedrich2015, abstract) |

Why seeding is safer here than in plain GP: in MAP-Elites, a seed can only hold the cells its behaviour falls into; it cannot take over the whole archive (mouret2015 describes the archive as "a map of high-performing solutions at each point in a space defined by dimensions of variation", abstract). Seeds still get offspring through parent selection, which is why a control run is required.

**Decision (changed r20):**
- **Random trees by PTC2** with sizes spread evenly up to the slot limit, replacing ramped half-and-half;
- **plus about 10 % named founders**, each with a stated reason (`docs/design_spec.md` §9.5), plus `founder:human` traders if you write any;
- **plus a required control:** every reported result includes a run **without founders** (O8). That shows whether the founders helped, rather than assuming it.

### A3. Identity, names, parents and descendants (Q3)

**Problems found in round 19's own proposal (fixed here):**
1. **An 8-hex id collides.** With n traders and 32-bit ids, the expected number of colliding pairs is about n²/(2·2³²). For 1 million traders that is about **116**; for 10 million about 11,600 (arith.). Ids must be longer.
2. **A genome hash is not an individual.** Two lineages can evolve the same genome at different times, from different parents. They are two organisms with identical genes (twins), and their histories must not merge.

**What the literature offers on lineages:**
- Lineage and phylogeny records are a standard way to understand evolutionary runs.
- Dolson et al. propose "lineage length, mutation accumulation, and phenotypic volatility", plus phylogeny measures such as "phylogenetic richness … and depth of the most-recent common ancestor" (dolson2020, abstract).
- Genealogy visualisation in GP: burlacu2013 tracks "genetic fragments" through mutation and crossover (abstract).
- Population-history analysis: mcphee1999 measures diversity from genetic histories and finds final GP populations keep little of it (GP Bibliography record).

**Decision (changed r20):**
- **Trader id** = run number + birth number, e.g. `R12-184213`. It is unique by construction, ordered by birth, and short.
- **Genome id** = SHA-256 of the canonical genome, shown as the shortest unique prefix of at least 10 hex characters (the way git shows commits). Identical genomes share a genome id, and the trader page says "same genes as R9-55120". The full hash is stored. With 10 hex characters (40 bits), 10 million traders give about 45 expected colliding pairs among the *displayed* prefixes, which is why the prefix grows until it is unique (arith.).
- **Behaviour id** (new) = a hash of the trader's bids on a fixed reference window. Different code with identical behaviour gets the same behaviour id. GP research calls a program's outputs on the test cases its *semantics* (uy2011; moraglio2012). Uses:
  - children whose behaviour equals their parent's are skipped (no wasted evaluation);
  - the effective number of trials for the deflated Sharpe ratio (G2) is counted on distinct behaviours.
- **Name** = two words derived from the trader id, e.g. `amber-heron`. Names are for memory, not uniqueness; the id is always shown next to the name, and search matches either.
- **Lineage store**:
  - every trader's birth record (id, parents, operator, seed, window, fitness, niche, death);
  - full genomes for archive members and all their ancestors;
  - everything else regenerated exactly from parents + operator + seed.
- **Phylogeny panel** on the Evolution page: number of surviving lineages, depth of the most recent common ancestor, lineage length and phenotypic volatility (dolson2020). It warns when the whole archive descends from one recent ancestor, a sign the search has narrowed.

### A4. How traders change: mutation and crossover (Q4)

**What the literature says:**

| Topic | Finding | Evidence |
|---|---|---|
| Crossover vs mutation | in GP, subtree crossover is often no better than mutation | angeline1997 (above); luke1998 (the revision of Luke & Spector 1997, whose results "were marred by statistical flaws"); white2009: crossover "does not significantly outperform mutation on most of the problems examined" (abstract) |
| Size-fair crossover | swapping subtrees of similar size limits growth | langdon2000sizefair: "considerably reduced increases in program size and no detrimental effect on GP performance" (abstract) |
| Bloat control | "the combination of depth limiting with such a punitive method is generally more effective than either alone" | luke2006bloat (abstract) |
| Tarpeian bloat control | randomly zeroing the fitness of some oversized programs | poli2003tarpeian: "zeroing the fitness of a certain proportion of the offspring that have above average length" (abstract) |
| Semantic operators | crossover guided by the subtrees' behaviour improves on standard crossover in regression | uy2011 (abstract). *Geometric* semantic GP (moraglio2012) makes children whose size grows fast: its operators "always produce offspring that are larger than their parents", giving "an exponential growth in the size of the individuals" (vanneschi2013, abstract), which would destroy readability |
| Constants | local optimisation of numeric constants helps GP | kommenda2020 (abstract), but by gradient methods, which our clearing thresholds make unusable |
| Continuous genes in MAP-Elites | "directional variation" (iso+line-DD), using correlations between elites, accelerates MAP-Elites | vassiliades2018 (abstract) |
| CMA-ME emitters | CMA-ES self-adaptation combined with a MAP-Elites archive | fontaine2019 (abstract); hansen2001 for CMA-ES itself |
| Operator rates | adaptive operator selection: adaptive pursuit (thierens2005), bandits (fialho2010) [both memory, verify] | in MAP-Elites, "a bandit algorithm dynamically finds the best selection of emitters" and improves quality, diversity and data efficiency (cully2021, abstract) |

**Decision (changed r20):**
- **Operators:** subtree mutation, point mutation, hoist/shrink, **size-fair crossover** (replacing plain subtree crossover), Gaussian constant mutation, category-set mutation. For numeric genes, **iso+line-DD by default** (replacing plain Gaussian); CMA-ME emitters later (O8).
- **Rates adapt:** a **multi-armed bandit** chooses among operators (and among three constant step sizes: 2 %, 10 % and 30 % of the feature's inter-quantile range), rewarding operators whose children enter or improve the archive. Each operator keeps a floor probability of 5 % so none dies out. The bandit's random draws are seeded, so runs stay byte-reproducible. The Evolution page shows each operator's success rate. That answers "how random" with data rather than a fixed table.
- **Neutral children are skipped:** a child whose behaviour id equals its parent's is not evaluated; the operator retries (up to 5 times). This is a lightweight use of semantics (uy2011); it saves evaluations without growing programs.
- **Bloat:** a hard size limit (about 15 nodes per slot) plus the parsimony term in fitness, the combination luke2006bloat found most effective.
- **Rejected:**
  - language-model mutation (A1);
  - geometric semantic operators (unreadable children);
  - gradient constant fitting (non-differentiable fitness).

---

## Part B. The other sixteen questions (Q5–Q20)

| Q | Decision | Status | Logic |
|---|---|---|---|
| Q5 reproduction | parents drawn from the archive with **rank weighting**, selection pressure p = 0.5 (0 = plain MAP-Elites) | delegated r20 (was R19-1) | gives more offspring to better traders, as asked, while p < 1 keeps every elite in play. Plain MAP-Elites selects uniformly (mouret2015); the QD framework lists selection variants such as curiosity (cully2017, abstract mentions "the large variety of variants"). **ε-lexicase on per-year results** (la_cava2016, abstract: effective for continuous problems; helmuth2015) is added to O8 as a robustness alternative: it favours parents that are best on random subsets of years |
| Q6 market time | evolution in compute time; **Life mode** (market-time ecology) added as M6b | delegated r20 (was R19-2) | the realism check Areeb asked for; Santa Fe market: traders "continually hypothesize … and confirm or discard these according to their performance" (arthur1997, abstract). Few generations (arith.: 4–10 in 20 years), so it complements rather than replaces MAP-Elites |
| Q6 training window | **changed r20: 5-year rolling training window** (step 1 year, walk-forward on the next year), was 1 year | changed r20 | see C1 |
| Q6 window comparability | **changed r20: when the window moves, every elite is re-evaluated on the new window** before any child is compared with it | changed r20 | see C2 |
| Q7 data | MISO DA and RT for every location downloaded (round 20); coverage in [data_coverage.md](data_coverage.md) | done r20 | Areeb's instruction |
| Q8 what bots see | past DA (to D−1) and final RT (to D−6) prices; gas, EPU, weather, capacity, calendar; **no futures** | delegated r20 (was R19-5) | no keyless 2005–2026 futures source exists; EIA's free series stop 2024-04-05 |
| Q8 decision time | **10:30 EPT on D−1 for every year** | delegated r20 (was round-18 D1) | never later than the true deadline (11:00 EST before 2016-11-05; 10:30 EPT since), so no look-ahead; one rule, one test. MISO's price files use hour-ending EST all year (obs. r20), so features align on EST hours |
| Q9 outside factors | gas, EPU as inputs; GPR, oil, World Bank as reporting only | kept | round 10–11 reasons (`docs/design_spec.md` §7.6–7.7) |
| Q10 costs | cost table by month/hour and era, labelled measured or estimate; placeholder rates until MISO's Rates Factors file arrives | delegated r20 (was round-18 D3) | building waits on nothing; labels keep it honest |
| Q11 settings | badges: Your choice / From market data / From the trader's account | kept (r19) | MPD and fees were wrongly shown as inputs |
| Q12 death | **out of money** = can't post collateral for the smallest bid; other layers optional | Areeb (r19); definition delegated r20 (was R19-4 (a)) | (a) is the realistic "can't trade any more" point; (b) equity ≤ 0 ignores collateral; (c) is offered as a "MISO-eligible" preset |
| Q13 best bot | highest **out-of-sample** fitness among gate-passing traders | kept (r19) | in-sample winners are the most overfitted (bailey2014charlatanism; bailey2017pbo) |
| Q14 refine | Refine runs on 2005–2025 only; trial counts carry over | kept (r19) | the deflated Sharpe must count every trial (bailey2014dsr: *J. Portfolio Management* 40(5), 94–107) |
| Q15 sealed test | once per run, logged, code-enforced separation; Forward test always available | kept (r19) | the hold-out's value is that nothing was tuned on it |
| Q16 grid map | axes net direction × selectivity; colour = fitness; blank = empty | kept; **colours changed r20** to greys (see D) | |
| Q17 explanations | every number has a one-line description; "What happened" paragraphs | kept; layout taken from the reference image (title, one-line description, value) | |
| Q18 UI separation | `app/` imports only `service`; import test | Areeb (r19) | |
| Q19 documentation | change ledger; every function/constant documented; locals by names + comments; **this rationale file** | Areeb (r19); locals delegated r20 (was R19-6) | |
| Q20 visual style | reference received in round 20; style in part D | Areeb (r20) | |

### C1. Why the training window changed from 1 year to 5 years
- **Statistical noise:** for roughly independent daily returns, the standard error of an annualised Sharpe ratio is about 1/√(years) (arith., from SE of a mean). On a 1-year window it is about **1.0**, so a trader with no edge routinely shows a Sharpe of ±1. On 5 years it is about **0.45**.
- **Trial budget:** the briefing's own MinBTL table (Claude Science reimplementation, unchecked against bailey2014charlatanism) allows about **3** independent trials at Sharpe 1 for 1 year, versus **45** for 5 years. Evolution runs hundreds of thousands of evaluations, so a 1-year window makes the archive's ranking mostly noise.
- **The 1-year choice came from the virtual-bidding papers** (4 of 8 use ~1-year windows; §11). Those papers re-estimate a forecasting model online, which is a different task from selecting a fixed rule that must survive many regimes.
- **Cost:** each evaluation replays 5 years instead of 1, so evaluations per hour fall about 5× at the same trader-years per hour. Accepted: fewer, more meaningful evaluations.
- **Kept configurable** (`training_window_years`); O8 compares 1, 3 and 5 years at equal compute.

### C2. Why elites are re-evaluated when the window moves
- The briefing's loop compares `child.F` with `archive[cell].F`. With a rolling window, the child may be scored on window W₂ and the elite on W₁, an unfair comparison.
- Elitist QD algorithms also handle noisy fitness badly. Justesen et al.: "current algorithms are all elitist, which make them unable to cope with stochastic fitness functions" (justesen2019, abstract). Flageat & Cully propose "deep grids" (flageat2020).
- **Fix:** at each window step, every elite is re-evaluated on the new window, and cells are re-decided. This is cheap: the archive has at most a few hundred elites, against thousands of children per step. Deep grids (several candidates per cell) stay an O8 option.

---

## Part C. Decisions from rounds 1–16 (from `decisions_log.md`) and their review

Round numbers are where a decision was **made** (a proposal in an earlier round is noted). "Superseded" means a later round replaced it; the later entry carries the current rule.

| ID | Decision | Round | Logic (from the log) | Round-21 review |
|---|---|---|---|---|
| D-01 | Portfolio project in OR/FE; realistic natural selection; bots die when they lose too much; score deployability; deploy | 1 | Areeb's goal (Q1) | kept; death rule refined in round 19 (D-66) |
| D-02 | Multi-instrument trading (futures, options, swaps) | 1 | first scope | **superseded** in round 4 by electricity virtual bidding; "not planned unless reopened" (`docs/design_spec.md` §16) |
| D-03 | Repo + `uv` lockfile; internet only for first install, never for market data | 1 (Q15) | reproducible, offline | kept (D-61) |
| D-04 | Own engine; Python + NumPy, GPU optional (Q10, Q14) | 1 | readability, speed | kept |
| D-05 | Deployment levels: L0 forward test, L1 paper-live on public data, L2 optional testnet, L3 real account out of scope | 2 | no broker needed for L0–L1 | kept. For MISO, L1 = the daily public report files (M9). MISO's sandbox ("CCE", `market_rules.md`) needs a registered participant, so L2 is out of scope, like L3 |
| D-06 | Interruptible sessions, checkpoints every ~10 min, budgets in evaluations, deflated Sharpe on the true count | 2 | laptop not on 24/7 | kept (`docs/design_spec.md` §11.1); the bandit and neutral-skip are seeded so resume stays byte-identical (A4) |
| D-07 | Exchange simulator with two fidelities (bar level + tick replay) | 2 | crypto realism | **superseded** in round 4: MISO's DA clearing is an auction, so one simulator with the price rule (D-24) suffices |
| D-08 | MAP-Elites as the showcase; CVT for >2 descriptors; re-evaluation for noisy fitness; CMA-MAE later | 2 | Areeb's choice | kept; re-evaluation made precise in round 20 (C2) |
| D-09 | Crypto (Binance perpetuals), then US energy futures | 2–3 | free derivatives data | **superseded** in round 4 |
| D-10 | `deployable/current_bot.json` refreshed at each checkpoint; "do nothing" fallback | 3 | a deployable bot at any time | kept; "best" defined in round 19 (§11.4) |
| D-11 | Five-layer career model (margin, mandate, hazard, CUSUM, peers); hazard enters fitness as a survival probability | 3 | "when a real trader would stop" | kept as optional layers; default death = out of money since round 19 |
| D-12 | Fitness = expected excess log-growth under the career model; QD gives visibility, not protection | 3 | punishes over-leverage by itself (zero excess growth at 2× Kelly; kelly1956 checked) | kept |
| D-13 | Baselines incl. do nothing, minimum size, random bots | 3 | anchors against luck | kept, adapted to MISO (§12.1) |
| D-14 | Market: electricity virtual trading | 4 | not covered by the surveyed papers and repos | kept. birge2017 (abstract): MISO arbitrage was limited by transaction costs, so the cost model matters |
| D-15 | Bot output per (node, hour): side, limit price, MW; P&L = cleared × q × direction × (RT − DA) − fees | 4 | the market's own mechanics | kept; fees made time-varying and netted (round 18) |
| D-16 | Map: net direction × selectivity | 4 (proposed), adopted with the spec | describes strategy kinds without using profit | kept; colours changed to greys (round 20) |
| D-17 | Look-ahead: decide at DA close; use DA ≤ D−1, RT ≤ D−2 | 4 | point-in-time | **superseded**: RT ≤ D−6 in round 15 (final RT is ~5 days late; preliminary RT is not archived, round 18); decision time 10:30 EPT every year (round 20) |
| D-18 | MISO primary, CAISO later | 5 | 0 of 8 papers study MISO; one all-node file per day | kept |
| D-19 | Location universe option E (hubs → clustered → all) | recommended 5, decided 6 | start small, scale later | kept; all-location data downloaded (round 20) |
| D-20 | Sealed 12-month hold-out 2025-09-22 → 2026-09-21, scored once per run, logged | 6 | an untouched test | kept; files stored apart since round 20 (§12.4) |
| D-21 | History option D: evolution from 2005-04-01 | 7 | more regimes; compensates for the hold-out | kept; the archive confirms 2005-04-01 is the first day (round 20) |
| D-22 | Consistency: inputs must cover 2005–2026 from one source; load forecasts and gas futures excluded | 7 | no data-driven regime breaks | kept |
| D-23 | Fixed persistent universe of 387 locations | 7 (proposed) | consistency | **superseded** in round 8 (D-24). Round 7 counted CINERGY/INDIANA as one persistent hub; the round-20 data shows they are **different node sets** (DA median abs. difference $0.23/MWh over 7,344 overlapping hours) |
| D-24 | Locations: whatever exists each day; bots choose by properties, never by name | 8 | a one-day bid strands nothing | kept |
| D-25 | Shocks: lagged GPR + EPU + Henry Hub as inputs; event calendar for reporting only | 8 (delegated) | mechanical, point-in-time indices | partly **superseded**: GPR moved to reporting in round 11 |
| D-26 | Weather: NWS Point Forecast Matrices via IEM, fetched once, parsed table bundled; ASOS reporting only | 8 | forecasts are what a trader sees | kept (not downloaded yet) |
| D-27 | Bundle hub prices 2005–2026 | 8 | offline use | kept; the hub table exists (round 20), bundling waits for the redistribution check |
| D-28 | 25 point-in-time features; fixed skeleton; typed GP ≤ ~15 nodes; rolling window; no language-model reading of news | 9 | readability; hindsight leak | kept; window lengthened to 5 years (C1); the hindsight argument also rules out language-model mutation (A1) |
| D-29 | Raw units; constants from each feature's historical range | 9 | readable formulas | kept |
| D-30 | Weather link: location → most-correlated hub (365 days) → NWS office | 9 | regional forecasts | kept; hub → office table still to decide (M1) |
| D-31 | `gpr` → `gas_vol_20d`; GPR reporting only; oil excluded | proposed 10, decided 11 | only energy-related threats matter to MISO | kept |
| D-32 | `month` → `wind_cap_region`, `loc_age_days` → `solar_cap_region` (EIA-860M) | proposed 10, decided 12 | capacity changes the price formation; count stays 25 | kept |
| D-33 | EPU kept | 11 | the only input that flagged COVID | kept |
| D-34 | Global gas prices reporting only | 11 | US–Europe gas correlation 0.16 | kept |
| D-35 | Career preset: an individual; prop trader and hedge fund optional | 13 | the realistic focus | kept |
| D-36 | Individual's floor from MISO's minimum capitalization ("$500k per a filing; a blog says $1M; verify at M0") | 13 | eligibility | **resolved** in round 18: Attachment L §III.C.1 requires $500k tangible net worth (or $5M assets) for a non-FTR participant, or $200k of financial security; §III.B's $1M net worth is one route to "appropriate person" status, not a floor |
| D-37 | Quit hazard calibrated to day-trader survival 44/24/15 % (Barber et al. 2020); CUSUM against risk-free + fixed costs; peers off | 13 | how real traders stop | kept as optional layers (round 19). barber2020 (abstract) confirms that unprofitable day traders quit more; the 44/24/15 % survival points are in the 2017 working paper (all day traders who traded ≥ 10 days, not only losers; round 27) |
| D-38 | Starting capital $1.5M, range $250k–$5M, configurable in `CapitalSettings`, TOML, CLI, explorer | 14, kept 16 | data-based default (tail headroom) | kept; **reproduced** in round 21 (`data/claude_science_check.csv`) |
| D-39 | Sizing rule: position_scale = min(1, 2 % × equity / p99 full-size loss) | 14 | a 1-in-100 day costs ≤ 2 % | kept |
| D-40 | Point-in-time p99: trailing 365 days, newest D−6, 90-day warm-up; the full-sample constant renamed CALIBRATION_ONLY | 15 | removes look-ahead | kept; the estimator's outputs are **reproduced exactly** in round 21 (eight table rows, range, median, 2.16 % breach rate by year) |
| D-41 | Liquidity cap min(5 MW, 5 % of median cleared MW); 936 MWh/day full size | 14; 936 confirmed 16 | stay a price-taker | kept; O9 tests it |
| D-42 | `daily_risk_budget` is the leverage knob; `credit_share` = share of capital pledged as collateral (default 25 %), which sets the Virtual MWh Limit; kept for stages D and C | 14 | collateral ($22k) is small against tail losses, so mark equity daily | kept. Resolves the round-19 question on `credit_share`'s meaning (`docs/design_spec.md` §13.1) |
| D-43 | Clearing: all-or-nothing by price, measured 99.5 % / 100 % agreement | 15 | realistic for small bids | kept |
| D-44 | Fixed costs $50k/year (assumed); cleared-share scenarios 1.0 / 0.721 / 0.25 | 15 | round-15 correction of $0.59/MWh | kept as assumption; no fixed MISO fee found (round 18) |
| D-45 | Relative ruin floor 2/3 by default; optional absolute floor; < 10 % headroom rejected | 16 | comparable careers at every capital | **superseded as default** in round 19: out-of-money death is the default, the floor is optional |
| D-46 | Storm-sensitivity helper (reporting only) | 16 | Uri and Elliott dominate tails | kept |
| D-47 | Size gene not added; tests first | 16 | it would saturate at g = 1 | kept |

**What round 20's reconstruction got wrong** (corrected above):
- **Round attributions:** the history start (round 7, not 6); option E (decided round 6, not 8); GPR to reporting (round 11, not 10); the feature swaps (round 12); fitness and current_bot.json (round 3, not 14); MAP-Elites (round 2); the map axes (round 4); the rolling window (round 9); the liquidity cap and $1.5M (round 14); the sizing rule (round 14, point-in-time in round 15); interruptible sessions (round 2); offline install (round 1).
- **Missing decisions:** deployment levels L0–L3 (D-05); the two-fidelity simulator (D-07, superseded); multi-instrument scope (D-02, superseded); the persistent universe (D-23, superseded); the round-4 look-ahead rule (D-17, superseded); the `credit_share` meaning (D-42); the round-13 capitalization question and its round-18 answer (D-36).
- **No conflicts** were found between the log and the current briefing: every difference is a later round replacing an earlier one, recorded above.

## Part D. Rounds 17–28

| ID | Decision (round) | Status | Logic |
|---|---|---|---|
| D-60 | UI option A: FastAPI + Jinja2 + one `theme.css` (17) | Areeb | editable without a build step |
| D-61 | Offline scope (a) (17) | Areeb | |
| D-62 | Standalone standard-library bot files (17) | Areeb; now generated at birth (A1) | |
| D-63 | Performance targets accepted (17) | Areeb; evaluations/hour 5× lower under C1 at the same trader-years/hour | |
| D-64 | Costs from MISO's documents; netting rules (18) | kept | `market_rules.md` §3 |
| D-65 | NERC holidays; a Sunday holiday also flags the Monday after (18, D2) | delegated r20 | covers both readings of the conflicting sources |
| D-66 | Default death = out of money (19) | Areeb | |
| D-67 | Trader as organism with generated code (19) | Areeb; refined r20 (A1) | |
| D-68 | Ids, names, lineage (19) | changed r20 (A3) | |
| D-69 | Founders (19) | changed r20 (A2) | |
| D-70 | Mutation operators (19) | changed r20 (A4) | |
| D-71 | Best bot, Refine, sealed test, grid map, badges, ledger, UI separation (19) | kept | |
| D-72 | Visual style from the reference image (20) | Areeb | below |
| D-73 | Build independently: rebuild missing files from the briefing and docs, prove them against the recorded numbers, ask directly (22) | Areeb | waiting blocked all milestones; `capital_sizing.md` specifies the slice well enough to rebuild and test it exactly |
| D-74 | Hub → NWS office by the nearest-load rule (23) | Areeb | one office per hub keeps each regional feature tied to one forecast; MISO's Illinois and Texas load sit in ILX's and LCH's areas, and Chicago is PJM. A two-office blend was rejected because it mixes in non-MISO weather |
| D-75 | Every day of cleared bids (23) | Areeb | liquidity caps measured on ~1,000 days instead of 33; O9 needs enough hub-hours for confidence intervals |
| D-76 | Stop only at the §2.4 check-ins (23) | Areeb | keeps momentum; the check-ins are where Areeb can test something real |
| D-77 | Capital explorer as a static page of Python-computed values (24, R24-1) | delegated | one formula source for the CLI, the explorer and the future Capital page; nothing to drift between Python and JavaScript |
| D-78 | "Well above full size" at ≥ 2× (24, R24-2) | delegated, assumption | the only threshold consistent with `capital_sizing.md` §10's expected warnings that is also a round number |
| D-79 | MISO data: build locally, never redistribute, with a user switch (24–25) | Areeb (25) | MISO's terms (read in round 25) forbid reproduction, distribution and derivative works; other sources are public domain or CC BY |
| D-80 | No scripted MISO access until decided (25) | Claude, pending Areeb | the terms forbid "automated means … to access … or copy"; stopping is reversible, continuing is not |
| D-81 | Keep all downloaded MISO data for private use (26) | Areeb | Areeb reads the fine print as restricting only commercial use; the pasted Terms of Use don't say so, so the source is [verify] and new scripted downloads stay paused |
| D-82 | Luke & Spector 1998 cited instead of their 1997 study; Angeline's Crossref-listed 1997 paper cited (27) | Claude | the 1997 study "was marred by statistical flaws" (the 1998 abstract); cite what can be checked |
| D-83 | `epu` history treated as revised data (27) | Claude | EPU revises the previous 30 days daily and keeps no vintages; the hindsight check (§8) already tests bots without `epu` |
| D-84 | The simulator never rejects a bid for its limit price (27) | Claude | caps specific to virtual bids weren't found; a limit beyond any cap only means "clear at any price", so results can't depend on the caps |
| D-85 | The report card flags price-insensitive bidding (27) | Claude | the IMM screens price-insensitive virtuals as potential manipulation; a deployable trader shouldn't look like one |
| D-86 | Fee and RSG history from MISO's Rates Factors workbook, downloaded by Areeb (28) | Areeb | the exact monthly and hourly costs; a manual browser download respects MISO's no-automated-access clause. Labelled estimates until it arrives |
| D-87 | Risk-free rate from FRED DTB3 (28) | Areeb | one keyless daily series covering 2005–2026, public domain; Treasury's own CSVs changed layout over the years; zero would flatter strategies in 2006–07 and 2023–25 |
| D-88 | Sunday NERC holiday flags the Sunday and the following Monday (28) | Areeb (confirms D2) | NERC keeps the holiday on the Sunday, but businesses observe the Monday, when load is holiday-low |
| D-89 | Battery round-trip efficiency default 82 % (28) | Areeb | EIA's measured 2019 US fleet average; 85 % was an unsourced assumption and 90 % flatters battery profit |
| D-90 | Each hub's weather from one fixed load-centre town (28) | Areeb | present in every year (town lists changed, e.g. 8 → 46 towns at Indianapolis in 2008); an average over a changing set would add breaks; a fixed-set average would mix Louisiana towns into TEXAS |
| D-91 | Generators assigned to the hub with the nearest load-centre town (28) | Areeb | one set of points for weather and capacity; a state table needs arbitrary picks for Iowa, Wisconsin, Missouri and Kentucky |
| D-92 | Daily series usable from the start of day t+lag, with one extra day where the posting time is unknown or after 10:30: T-bill and EPU/GPR 2 days, gas and oil 1 business day (28) | Claude | the briefing's "lag 1 day" didn't say when in the day; H.15 posts in the afternoon and EPU/GPR at unrecorded times, so the cautious reading can't see anything early. Reversible |

## Part E. Visual design (Q20)

**The reference image** shows:
- a narrow left navigation of text items with a nested sub-menu;
- a page title with a search field and the user at the top right;
- a filter line with plain-text actions ("Add filter", "Edit data");
- content panels, each with a **title, a one-line plain-English description, and the value or chart**.

**Areeb's direction:** even simpler, less colourful, no large boxes for buttons, only clickable words. Grey backgrounds were already excluded in round 19.

**What we take from it:**
- the **title + one-line description + value** pattern for every metric. It is exactly the explanation rule of Q17;
- a left text navigation with a nested sub-list;
- filters and actions as plain words on one line.

**What we change:**

| Reference | evobots |
|---|---|
| black navigation panel | white; navigation is text, separated from content by one hairline |
| panels with grey fill and rounded borders | no fills: panels are separated by whitespace and 1-px hairlines, square corners |
| boxed buttons and inputs | **clickable words only** (underlined on hover); the one text input (search) is a single bottom rule |
| coloured chart lines and bars | **ink only**: primary series in near-black, a second series dashed, gridlines hairline. **One signal colour** (a muted red) is reserved for losses and deaths |
| coloured heat bars | grid map in **greys** (white = empty, darker = higher fitness); a profit view uses the same greys with red only for negative values |

**Tokens** (`app/static/theme.css`; all values in one place):
- **ink** `#111111`; **secondary text** `#5f5f5f`; **hairline** `#e4e4e4`; **background** `#ffffff`; **signal** `#a3271f`. There are no other colours.
- **Fonts:** the system font stack only (offline; no web fonts); numbers in tabular figures.
- **Type sizes:** 12 / 14 / 16 / 22 px. **Spacing:** 4 / 8 / 16 / 24 / 40 px.
- **No** shadows, gradients, rounded boxes, or icons (except the one-character "?" for help).

A static preview of these rules, built by Python from the real downloaded data, is in `design/preview_data_page.html` (round 20).

---

## Part F. Changes to make in `docs/design_spec.md` (done in round 20)
1. §9.4: ids, behaviour id, names (A3).
2. §9.5: PTC2 and the no-founder control (A2); `founder:human` (A1).
3. §9.6: size-fair crossover, iso+line-DD, bandit operator selection, neutral skip (A4).
4. §11: 5-year window (C1); re-evaluation of elites on window moves (C2); the phylogeny panel (A3).
5. §14.5 and §15: the visual rules of part E.
6. §17.3: R19 choices resolved under delegation; round-18 D1–D3 resolved.
7. §7.0 and §3: data downloaded.
