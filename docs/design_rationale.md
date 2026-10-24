# Design rationale: the logic behind every decision

A living write-up. Every design decision in evobots has an entry here: what was decided, why, what the literature says, what was rejected, and its status. **Update this file whenever a decision is made or changed.** The change ledger (`change_ledger.md`) records *when*; this file records *why*.

- Started in round 20 (2026-10-24). It covers:
  - the decisions of rounds 1–16 as recorded in the briefing (`CLAUDE.md`);
  - rounds 17–19;
  - Areeb's 20 review questions (`rounds/round19_prompt_review.md`).
- The decision logs from rounds 1–16 (`docs/decisions_log.md`) **have not been uploaded to the repository**. Entries D-01 … D-45 are reconstructed from the briefing's summaries. When the logs arrive, each entry will be reconciled with them and any difference reported.
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
- References are keyed as in [references.md](references.md). Every key there was checked against Crossref or arXiv by `tools/check_references.py`. Entries marked "not found" are always cited with [verify].

---

## Part A. The four questions on the trader itself (Q1–Q4), with the literature

### A1. What a trader is: representation and its own code (Q1)

**The question:** What makes each trader an organism? Does it have its own executable code you can open with a button?

**Options found in the literature:**

| Option | What it is | For | Against |
|---|---|---|---|
| **Typed tree GP** (Montana 1995) | programs as syntax trees; every function has argument and return types, and only well-typed trees are created | "enforces data-type constraints", avoiding "unnecessarily large search times and/or unnecessarily poor generalization" (montana1995, abstract); trees print directly as readable code | bloat (trees grow without gain); crossover can act like random macro-mutation (Angeline 1997, not found: [verify]) |
| **Grammar-guided GP** (Whigham 1995 [verify]; survey mckay2010) | a grammar defines the language; trees are derivations of it | the whole trader language lives in one readable file; units are grammar categories | same search behaviour as typed GP; no extra benefit here beyond documentation |
| **Grammatical evolution** (oneill2001) | an integer string is mapped through a grammar into a program | simple genome | small genome changes can make large program changes (low locality) (memory) [verify]; harder to trace why a child differs |
| **Linear GP** (brameier2007) | a sequence of register instructions | fast to run | hard to read; much non-functional code |
| **Cartesian GP** (miller2000) | a fixed-size graph of nodes | reuses sub-expressions; neutral drift | hard to read as a rule |
| **PushGP** (spector2002) | stack-based programs with types, loops and self-modification | very general | far more power than a daily bid rule needs; hard to read |
| **Self-replicating machine code** (Tierra: Ray 1991 [verify]; Avida: ofria2004) | each organism *is* executable code that copies itself and mutates | the literal "organism with its own code"; Avida is a platform for "self-replicating and evolving computer programs" (ofria2004, abstract) | built to study evolution, not to find good trading rules; most mutants don't work; unreadable |
| **Neural networks** (e.g. NEAT, stanley2002) | evolving network weights and topology | flexible | opaque. Rudin argues for "models that are interpretable in the first place" for high-stakes decisions (rudin2019, abstract). Rejected in round 9 for opacity and overfitting with ~20 years of data |
| **Language-model mutation of source code** (ELM: lehman2022; FunSearch: romeraparedes2024) | a language model proposes code edits; an evaluator keeps the good ones | edits the literal source; ELM with MAP-Elites produced "hundreds of thousands of functional examples of Python programs" (lehman2022, abstract) | **hindsight leak**: a language model has read about 2005–2026 markets and can steer rules toward known history, the same reason news-reading was rejected in round 9; needs the internet or a large local model (breaks offline, §14.4); not byte-reproducible (breaks the resume test, §11.1) |

**What GP trading studies report** (why readable, constrained rules and honest testing matter):
- Allen & Karjalainen (1999) evolved trading rules for the S&P index: positive excess returns after costs in one test period (1970–89), but "using data for other periods since 1929, the rules … do not lead to excess returns after transaction costs" (allen1999, abstract).
- Neely, Weller & Dittmar (1997, neely1997) found GP rules profitable in FX out of sample (memory) [verify].
- Bhattacharyya, Pictet & Zumbach (2002, bhattacharyya2002) used domain-knowledge constraints on GP trading rules, reporting better out-of-sample results (memory) [verify].
- Chen & Navet (2007, chen2007) proposed testing GP traders against random-search baselines to tell an efficient market from an inefficient algorithm (memory) [verify]. This supports the "random bots" baseline (§12.1).

**Decision (changed r20 in detail, kept in substance):**
1. **Typed tree GP with a fixed skeleton**, written as one **typed grammar file** (`bots/grammar.py`): the "trader language", readable on its own page. Types include units, so `spread + temperature` can't be written. Typed GP and grammar-guided GP give the same search here; the grammar form is chosen because it doubles as documentation.
2. **The organism's code:** each trader's genome is compiled into a standalone Python file the moment it is born. The **View code** button shows that file. The engine and the file must agree exactly, checked by a test.
3. **New in r20: the code can be read back.** The generated dialect is parsed back into a genome. You may edit a trader's file (or write one), and if it passes the grammar and unit checks it becomes a **founder** in a Refine run, labelled `founder:human`. Seeding with human-designed programs is studied in GP (langdon2000seeding; content (memory) [verify]).

**Rejected:** self-replicating machine code (not built for finding rules; unreadable); neural networks (opaque); language-model mutation (hindsight leak, not offline, not reproducible).

### A2. What traders start with (Q2)

**Options:**

| Option | For | Against |
|---|---|---|
| **Ramped half-and-half** (Koza 1992, not found: [verify]) | the classic mix of tree shapes | poor control over tree *size*; with a ~15-node limit many trees are cut or rejected |
| **PTC2** (luke2000ptc) | builds random trees with a chosen size distribution (memory: designed for that) [verify] | slightly more code |
| **Random only** | no human bias | wastes early evaluations; may never find simple, known strategies |
| **Seeded with known strategies** (langdon2000seeding; friedrich2015) | starts from sensible traders | seeds can take over the population and reduce diversity (burke2004 studies diversity measures; content (memory) [verify]); the benefit depends on the algorithm: "different optimization algorithms benefit very differently from seeding" (friedrich2015, abstract) |

Why seeding is safer here than in plain GP: in MAP-Elites, a seed can only hold the cells its behaviour falls into; it cannot take over the whole archive (mouret2015 describes the archive as "a map of high-performing solutions at each point in a space defined by dimensions of variation", abstract). Seeds still get offspring through parent selection, which is why a control run is required.

**Decision (changed r20):**
- **Random trees by PTC2** with sizes spread evenly up to the slot limit, replacing ramped half-and-half;
- **plus about 10 % named founders**, each with a stated reason (`CLAUDE.md` §9.5), plus `founder:human` traders if you write any;
- **plus a required control:** every reported result includes a run **without founders** (O8). That shows whether the founders helped, rather than assuming it.

### A3. Identity, names, parents and descendants (Q3)

**Problems found in round 19's own proposal (fixed here):**
1. **An 8-hex id collides.** With n traders and 32-bit ids, the expected number of colliding pairs is about n²/(2·2³²). For 1 million traders that is about **116**; for 10 million about 11,600 (arith.). Ids must be longer.
2. **A genome hash is not an individual.** Two lineages can evolve the same genome at different times, from different parents. They are two organisms with identical genes (twins), and their histories must not merge.

**What the literature offers on lineages:**
- Lineage and phylogeny records are a standard way to understand evolutionary runs.
- Dolson et al. propose "lineage length, mutation accumulation, and phenotypic volatility", plus phylogeny measures such as "phylogenetic richness … and depth of the most-recent common ancestor" (dolson2020, abstract).
- Genealogy visualisation in GP: burlacu2013 (memory) [verify].
- Population-history analysis: McPhee & Hopper 1999 (not found: [verify]).

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
| Crossover vs mutation | in GP, subtree crossover is often no better than mutation | angeline1997 (not found: [verify]); luke1997 ([verify]); white2009 "a rigorous evaluation of crossover and mutation" (memory) [verify] |
| Size-fair crossover | swapping subtrees of similar size limits growth | langdon2000sizefair (memory) [verify] |
| Bloat control | "the combination of depth limiting with such a punitive method is generally more effective than either alone" | luke2006bloat (abstract) |
| Tarpeian bloat control | randomly zeroing the fitness of some oversized programs | poli2003tarpeian (memory) [verify] |
| Semantic operators | crossover guided by the subtrees' behaviour improves on standard crossover in regression | uy2011 (abstract). *Geometric* semantic GP (moraglio2012) makes children whose size grows fast (memory) [verify], which would destroy readability |
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
| Q9 outside factors | gas, EPU as inputs; GPR, oil, World Bank as reporting only | kept | round 10–11 reasons (`CLAUDE.md` §7.6–7.7) |
| Q10 costs | cost table by month/hour and era, labelled measured or estimate; placeholder rates until MISO's Rates Factors file arrives | delegated r20 (was round-18 D3) | building waits on nothing; labels keep it honest |
| Q11 settings | badges: Your choice / From market data / From the trader's account | kept (r19) | MPD and fees were wrongly shown as inputs |
| Q12 death | **out of money** = can't post collateral for the smallest bid; other layers optional | Areeb (r19); definition delegated r20 (was R19-4 (a)) | (a) is the realistic "can't trade any more" point; (b) equity ≤ 0 ignores collateral; (c) is offered as a "MISO-eligible" preset |
| Q13 best bot | highest **out-of-sample** fitness among gate-passing traders | kept (r19) | in-sample winners are the most overfitted (bailey2014charlatanism; bailey2017pbo) |
| Q14 refine | Refine runs on 2005–2025 only; trial counts carry over | kept (r19) | the deflated Sharpe must count every trial (Bailey & López de Prado, deflated Sharpe ratio, [verify] publication details) |
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

## Part C. Decisions from rounds 1–16 (reconstructed from the briefing) and their review

| ID | Decision (round) | Logic | Round-20 review |
|---|---|---|---|
| D-01 | Goal: natural selection of trading bots that is realistic, reports deployability, and can deploy (1) | Areeb's goal | kept |
| D-02 | Market: MISO virtual bidding (4–5) | free, keyless, large; none of the 8 virtual-bidding papers studies MISO; none uses evolution or QD | kept. Birge et al. found MISO arbitrage limited by transaction costs and some participants betting against the gap (birge2017, abstract), so costs (D-21) matter |
| D-03 | Crypto and energy futures rejected (4–5) | pumps and whales; futures heavily optimised and free data ends 2024 | kept |
| D-04 | Periods: evolution 2005-04 → 2025-09-21, sealed hold-out 12 months, forward after (6) | every season once; includes the 2026 Iran war | kept; the hold-out files are physically separate since round 20 |
| D-05 | Consistency principle: inputs exist 2005–2026 from one source (7) | no regime breaks from data changes | kept |
| D-06 | Location universe option E: hubs → clustered → all (8) | start small and readable, scale later | kept; all-location data now downloaded |
| D-07 | Weather from NWS forecasts via IEM, latest issue before the deadline (8) | the forecast is what a trader sees; actuals would leak | kept |
| D-08 | No language-model reading of news (9) | hindsight leak; no consistent archive; news moves both DA and RT | kept; the same argument now also rules out language-model mutation (A1) |
| D-09 | Bots are small typed formulas, not neural nets (9) | readability; overfitting with ~20 years | kept, strengthened (A1, rudin2019) |
| D-10 | GPR reporting only (10) | most geopolitical threats don't touch MISO's fuel | kept |
| D-11 | EPU kept as an input (11) | the only input that flagged COVID | kept |
| D-12 | 25 features in raw units (12) | readability; unit checking | kept |
| D-13 | Missing input makes comparisons false (12) | a bot never trades on missing data | kept |
| D-14 | Hindsight check on `epu` and `gas_*` (12) | detects edges only possible with hindsight | kept |
| D-15 | Career: an individual trader (13) | the realistic default for a portfolio project | kept; death rule changed (D-46) |
| D-16 | Quit hazard calibrated to Taiwanese day traders (13) | direction and speed of quitting | now optional (r19). barber2020 (abstract): "unprofitable day traders are more likely than profitable traders to quit"; the 44/24/15 % survival points are still [verify] |
| D-17 | CUSUM retirement (13) | opportunity cost; edge decay | now optional (r19); page1954 checked |
| D-18 | Fitness = expected log-growth over risk-free minus parsimony (14) | log-growth punishes over-leverage (Kelly; kelly1956 checked) | kept |
| D-19 | MAP-Elites with net direction × selectivity (14) | diversity of strategy kinds, not one winner | kept |
| D-20 | Rolling 1-year window (14) | literature on virtual bidding | **changed r20 to 5 years** (C1) |
| D-21 | Clearing rule by price; all-or-nothing (15–16) | 99.5 % agreement with the cleared-bids report | kept; the rare partial fills happen when the price equals the bid (`market_rules.md` §1) |
| D-22 | Price-taker with 5 MW / 5 % liquidity cap (16) | our size is small against hub volume | kept; O9 tests it |
| D-23 | $1.5M starting capital (15–16) | covers the trailing tail at 2 % daily risk | kept |
| D-24 | Sizing rule on trailing p99 (D−6, 365 days, 90-day warm-up) (15) | point-in-time risk sizing | kept; O5 tests better tail estimators |
| D-25 | Size gene not adopted (16) | it would saturate at 1 | kept |
| D-26 | Report-card gates G1–G8 (14) | multiple defences against overfitting | kept; G2 uses distinct behaviours (A3) |
| D-27 | Deployable bot at every checkpoint; "do nothing" fallback (14) | usable after every session | kept |
| D-28 | Determinism and byte-identical resume (14) | trustworthy long runs on a laptop | kept; the bandit and neutral-skip are seeded (A4) |
| D-29 | Stack: Python 3.13, uv, NumPy, Numba, own GP and MAP-Elites (planning) | readable, fast, no heavy frameworks | kept |
| D-30 | Offline at run time (planning) | works on the laptop without internet | kept |
| D-31 | Storm sensitivity reporting (16) | Uri and Elliott dominate tails | kept |

## Part D. Rounds 17–20

| ID | Decision (round) | Status | Logic |
|---|---|---|---|
| D-40 | UI option A: FastAPI + Jinja2 + one `theme.css` (17) | Areeb | editable without a build step |
| D-41 | Offline scope (a) (17) | Areeb | |
| D-42 | Standalone standard-library bot files (17) | Areeb; now generated at birth (A1) | |
| D-43 | Performance targets accepted (17) | Areeb; evaluations/hour 5× lower under C1 at the same trader-years/hour | |
| D-44 | Costs from MISO's documents; netting rules (18) | kept | `market_rules.md` §3 |
| D-45 | NERC holidays; a Sunday holiday also flags the Monday after (18, D2) | delegated r20 | covers both readings of the conflicting sources |
| D-46 | Default death = out of money (19) | Areeb | |
| D-47 | Trader as organism with generated code (19) | Areeb; refined r20 (A1) | |
| D-48 | Ids, names, lineage (19) | changed r20 (A3) | |
| D-49 | Founders (19) | changed r20 (A2) | |
| D-50 | Mutation operators (19) | changed r20 (A4) | |
| D-51 | Best bot, Refine, sealed test, grid map, badges, ledger, UI separation (19) | kept | |
| D-52 | Visual style from the reference image (20) | Areeb | below |

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

## Part F. Changes to make in `CLAUDE.md` (done in round 20)
1. §9.4: ids, behaviour id, names (A3).
2. §9.5: PTC2 and the no-founder control (A2); `founder:human` (A1).
3. §9.6: size-fair crossover, iso+line-DD, bandit operator selection, neutral skip (A4).
4. §11: 5-year window (C1); re-evaluation of elites on window moves (C2); the phylogeny panel (A3).
5. §14.5 and §15: the visual rules of part E.
6. §17.3: R19 choices resolved under delegation; round-18 D1–D3 resolved.
7. §7.0 and §3: data downloaded.
