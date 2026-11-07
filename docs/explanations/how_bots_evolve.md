# How the bots start and how they evolve

What every trader is made of, where the first ones come from, how new ones are bred, and what actually happened in run R101 (30,000 traders on MISO data, 2005–2025). Code references are to `src/evobots/`; formulas are in [maths.md](../maths.md) §5. The search itself is in [qd_explained.md](../qd_explained.md).

## 1. One shape for every trader
A bot doesn't change while it lives. Its genome is fixed at birth. *Evolution* means its children differ from it. Every trader has exactly the same shape (`bots/trader.py`):

| Part | What it is | Kind |
|---|---|---|
| **where** | which location-hours it considers | a true/false formula tree |
| **when** | a second condition, usually about time | a true/false formula tree |
| **score** | its forecast, in $/MWh: above 0 means "RT will be above DA" | a number formula tree |
| **side** | DEC if score > the DEC threshold; INC if score < −(the INC threshold); else no bid | 2 numbers, $0–20/MWh each |
| **price** | limit = yesterday's DA ± an offset | 1 number, $0–100/MWh |
| **size** | location cap × size fraction × min(1, \|score\| ÷ a score scale) | 2 numbers |
| **risk** | the most of its daily footprint it may bid; after a day losing more than X % of equity, sit out N days | 3 numbers |

- **Which parts evolve:** the three formula trees and the eight numbers.
- **Which parts never do:** the hard limits. Each location's MW cap, death when out of money, and the rule that a bot sees only what was public at 10:30 the day before are outside the genome and can't mutate.

### The formula language
A formula tree is built from (`bots/grammar.py`):
- **Inputs:** any of the 25 data inputs ([features.md](../features.md)), such as "average DA − RT spread, last 7 visible days" or "forecast cooling degree-days".
- **Numbers:** constants, each carrying a unit.
- **Arithmetic:** `+ − × ÷ min max abs` and `if … then … else`.
- **Conditions:** `> <`, `and or not`, "location type in {Hub, Loadzone}", "is a holiday", "always".

**Every tree is unit-checked.** You can't add °F to $/MWh, and the score must come out in $/MWh. So every child that evolution makes is a valid program: evolution edits trees, never Python text. A tree slot holds at most 15 nodes.

**A missing input means no bid.** For example, a hub that didn't exist yet has no prices, so a bot never trades on it.

### The same bot, three ways
Every bot can be shown three ways:
- as plain English (the Trader page);
- as a standalone Python file (`evobots export-bot`), which parses back into the same genome;
- as canonical JSON, whose SHA-256 is its genome id.

## 2. The starting population (the first 70)
There is no single standard starting bot. A fresh run's first batch is 70 traders (`qd/run.py`, `starting_children`).

### 7 hand-written founders (`bots/founders.py`)
Each is small and has a stated reason:

| Founder | Rule | Why |
|---|---|---|
| always_inc | INC at every location-hour | DA has averaged slightly above RT at every hub |
| always_dec | DEC at every location-hour | the mirror; profits in RT spikes |
| persistence | follow the sign of the last visible week's spread | the standard baseline |
| premium_follow | bet the last 28 days' premium continues | premiums persist |
| premium_fade | bet it reverses | premiums mean-revert |
| heat_dec | DEC on hot weekday afternoons (forecast cooling degree-days) | hot days may surprise RT upward [unverified hypothesis] |
| wind_inc | INC when forecast wind × wind capacity is high | windy days may push RT down [unverified hypothesis] |

### 63 random traders
- **The trees** are built by PTC2 (Luke 2000), which spreads tree sizes evenly up to 15 nodes. *where* and *when* are left empty ("always") 40 % of the time each; *score* always gets a random formula.
- **The constants** are drawn from each input's real 5th–95th percentile range.
- **The numbers** are uniform in their allowed ranges. 30 % of random traders also get a pause rule.

A run without founders (`evobots run --no-founders`) starts from 70 random traders. That is the control experiment for "do the hand-written ideas help?"

A **Refine** run instead starts from one chosen trader and 69 mutants of it.

## 3. How a child is made
After the first batch, every trader is bred from the map (`qd/run.py`, `bred_children`).
1. **Pick the operator.**
   - **What it is:** an adaptive "bandit" (`bots/variation.py`). Each operator has a score that rises when its children enter or improve the map; better operators get chosen more, but none drops below 5 %.
   - **Starting weights:** constant tweaks 30 %, subtree 25 %, point 20 %, crossover 15 %, hoist 10 %.
2. **Pick parents.** Two draws from the map's elites, ranked by fitness. With selection pressure p = 0.5, half the draw favours the better elites and half is uniform, so weaker kinds of trader still get children (§11.2).
3. **Apply the operator:**

   | Operator | What it does |
   |---|---|
   | constant (small 2 %, medium 10 %, large 30 %) | nudges one constant by that share of its range; for the numeric genes, also a step toward another elite's values (iso+line-DD, Vassiliades & Mouret 2018) |
   | subtree | replaces a branch with a new random branch of the same type and unit |
   | point | swaps one node for a compatible one: `+`↔`−`, `>`↔`<`, `and`↔`or`, an input for another with the same unit |
   | hoist | replaces a branch with one of its own sub-branches (shrinks the code) |
   | crossover | swaps in a similar-sized, unit-matched branch from the other parent (size-fair, Langdon 2000) |

4. **Skip copies.** If the child bids exactly like its parent on a fixed reference period, its behaviour id is the same, and it is re-made (up to 5 tries), so no evaluation is wasted on a copy.
5. **Record it.** Every child gets a birth record: id, parents, operator and random seed. Any trader can be rebuilt exactly from its parents, and a resumed run is byte-identical to an uninterrupted one.

## 4. How a child is judged and kept
1. **Score it as a career** on the current 5-year training window. It starts with $1.5M and sizes its bids by its own recent worst losses. It pays MISO's fees, can be cut by the daily cap and the credit limit, and dies if it runs out of money. Its fitness is its log growth beyond the risk-free rate, minus 0.002 per formula node, so a simpler rule wins a tie ([maths.md](../maths.md) §5.1).
2. **Place it on the map** (`qd/archive.py`). The map is a 10 × 8 grid by *behaviour*:
   - across, from "only INC" to "only DEC";
   - up, from "bids on 0.1 % of location-hours" to "bids on all of them".

   The child takes its cell if the cell is empty or if it beats the elite there. That is MAP-Elites (Mouret & Clune 2015): the run keeps the best trader of each *kind*, not just one champion, so the search keeps many different ideas alive.
3. **The window moves forward a year** once the window's share of the budget is spent (the budget ÷ the number of windows; 2,000 traders in R101). Every elite is re-scored on the new window and the cells are re-decided, so the population has to keep working as the market changes. Each elite is also scored on the year after its window, which the search never trains on.

## 5. What happened in R101 (obs.)
- **Who made the traders:**
  - 70 starters: 7 founders and 63 random;
  - 29,930 bred children.
- **Operators used:**

  | Operator | Children |
  |---|---|
  | small constant | 8,390 |
  | medium constant | 7,250 |
  | crossover | 3,762 |
  | large constant | 3,467 |
  | point | 2,445 |
  | subtree | 2,436 |
  | hoist | 2,180 |

- **Family lines** reach generation 177.
- **Fitness of traders entering the map rose.** Their average went from −0.12 in the first tenth of the run to +0.19 by the middle. After that it is about +0.1, because the window keeps moving forward every 2,000 traders, and fitness on different windows isn't on the same scale.

### The best candidate's family tree
R101-29627, "frosty-raven", was born 29,627th, at generation 173.
- **Ancestors:** 2,035. They go back to 16 random starters and one founder, **premium_follow**.
- **Its direct line from premium_follow:** 76 steps:

  | Step | Count |
  |---|---|
  | small constant | 40 |
  | medium constant | 19 |
  | crossover | 8 |
  | large constant | 4 |
  | subtree | 2 |
  | hoist | 1 |
  | point | 1 |

- **Where it started:** premium_follow's rule was "score = −1 × the last 28 days' average spread".
- **Where it ended up** (11 nodes):

  ```
  score: −0.08 × (yesterday's DA price + 0.41 $/MWh per point × policy uncertainty)
  side:  INC if score < −9.41 (i.e. yesterday's DA + 0.41 × EPU > about $117/MWh),
         DEC if score > 1.3 (in practice rare: DA prices are almost always positive)
  price: limit = yesterday's DA ∓ $93.9;   size: 99 % of the cap;   daily cap 84 %
  ```

  In words: **sell day-ahead power (INC) after expensive days in uncertain times.** Evolution swapped the spread input for yesterday's price, added the policy-uncertainty index through crossover, and spent most of its steps tuning the constants.
- **Bloat:** the evolved formula still contains `max(EPU, EPU)`. It's harmless, and it's what the 0.002-per-node penalty and the hoist operator work against.

### Why it isn't called deployable
On its unseen year it made +5 %, survived every storm and stayed positive with doubled costs. It fails two tests:
- **Luck (G2):** on its last training window it isn't distinguishable from what the luckiest of ~1,000 effective trials would show.
- **Overfitting (G3):** the run's in-sample winners usually weren't its out-of-sample winners.

[report_card.md](../report_card.md) explains the gates.

## 6. Where to look
- **Evolution page:** the map, the operator scores, family lines and the current decision.
- **Traders page:** search 30,000 traders by id, name, origin or operator.
- **Trader page:** the rules, the generated code, its life, what it saw on a day, and its family tree.
- **Code:** `bots/trader.py` (shape), `bots/grammar.py` (language), `bots/founders.py`, `bots/random_trees.py`, `bots/variation.py` (operators and bandit), `qd/run.py` (the loop), `qd/archive.py` (the map).
