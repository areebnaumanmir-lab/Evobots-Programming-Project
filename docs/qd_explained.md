# How the search works: MAP-Elites over traders

Explanation document for M6 (`docs/design_spec.md` §11). Code: `src/evobots/qd/`.

## 1. Why a map, not a single winner
A plain genetic algorithm keeps the fittest traders and converges on one kind of strategy. MAP-Elites (Mouret & Clune 2015) instead keeps **the best trader of each kind**. Kinds are cells of a map with two axes:
- **Net direction** (horizontal): (DEC MWh − INC MWh) ÷ cleared MWh, from −1 (only INC: bets that DA prices exceed RT) to +1 (only DEC).
- **Selectivity** (vertical): the share of priced location-hours the trader bids on, log scale from 0.1 % to 100 %.

A white cell means no surviving trader of that kind has been found yet. The map shows how many different kinds of strategy survive and where the profitable ones are. Diversity gives choice, not protection: risk control comes from the fitness and the career model (§10.2).

## 2. One batch
1. **Parents** are drawn from the elites with rank-weighted selection, P(i) = (1 − p)/n + p × rank weight. Pressure p = 0.5 (round 20): fitter traders get more offspring, and p = 0 is plain MAP-Elites.
2. **An operator** is chosen by the bandit (`src/evobots/bots/variation.py`): subtree, point, hoist, size-fair crossover, or a constant step of 2 %, 10 % or 30 %. Operators whose children enter the archive are chosen more often, and every operator keeps at least 5 %.
3. **Neutral children are skipped:** a child that bids exactly like its parent on the reference window (same behaviour id) is redrawn, up to 5 times.
4. **Children are scored** on the current 5-year window: bids, settlement, career, fitness. Dead traders are discarded (natural selection).
5. **A child takes a cell** if the cell is empty or it beats the incumbent's fitness.

## 3. Windows move through history
The training window is 5 years, stepped by 1 year (round 20): 1 year gives a Sharpe ratio's standard error of about 1.0, 5 years about 0.45. When the window moves, every elite is **re-evaluated on the new window before any child is compared with it**, so no trader is judged against a score from different data. Each elite is also scored on the **next unseen year** (walk-forward) at checkpoints.

## 4. Two counters instead of generations
MAP-Elites has no strict generations, so the app shows two counters:
- **batches done**: how many rounds of children;
- **lineage depth**: the longest chain of ancestors (generation = 1 + the deepest parent's).

## 5. Determinism, resume and lineage
- Every random draw comes from the run's seeded generator. Each child's variation uses its own stored seed.
- A resumed run is byte-identical to an uninterrupted one (`tests/test_search.py::test_resume_is_byte_identical`). The number of worker processes doesn't change the result.
- The lineage store (`runs/<id>/lineage.sqlite`) keeps a birth record for every trader. It stores the genomes of archive entrants and their ancestors; every other trader is regenerated exactly from its parents, operator and seed (`::test_every_trader_regenerates_from_its_birth_record`).

## 6. The best bot, or "do nothing"
At every checkpoint the top 10 elites are scored on the next unseen year and run through the quick gates (`src/evobots/qd/gates.py`):
- **G1 survival:** stationary-bootstrap paths stay within a 50 % loss mandate in 95 % of paths.
- **G2 skill vs trials:** deflated Sharpe ≥ 0.95, with the effective number of trials (participation ratio of a reservoir of the run's P&L streams, scaled to all distinct behaviours, plus a Refine run's prior trials). The benchmark variance is the null sampling variance 1/(T − 1) (round 37).
- **G4 cost stress:** positive growth on the unseen year with doubled costs.
- **G6 walk-forward:** positive growth on the unseen year with drawdown within the mandate.

The **best bot** is the passing elite with the highest walk-forward fitness; ties go to the smaller program. It is never the highest in-sample profit, which is usually the most overfitted. If none passes, `runs/<id>/deployable/current_bot.json` says **"do nothing"** and names the nearest candidate and the gate it failed.

## 7. Does it find real signals, and nothing in noise?
`tests/test_search.py` plants a rule in synthetic data: RT is raised by $6/MWh in hours 14–19 when the forecast high exceeds 85 °F, at 2.5 % of hub-hours.
- After 2,400 traders, the best bot DECs in afternoon hours scaled by cooling degree-days. It bids on 100 % of planted hub-hours, and 19 % of its DEC bids land on them (7.6× the base rate). The archive also holds a precise variant (precision 100 %, recall 43 %).
- On pure noise the same search answers "do nothing".

## 8. Life mode (M6b)
`src/evobots/qd/life.py` lets a population live through the history day by day:
- traders trade every day they are alive;
- they die when out of money;
- they reproduce when their equity reaches 2× the starting capital, handing that capital to a mutated child that starts trading the next day.

It is the literal natural selection of the project's goal and a realism check, not the search engine. Compute time is not market time, so the MAP-Elites search replays history in seconds, while Life mode gets only a handful of generations in 20 years.

## 9. Commands
- `evobots run --evaluations 20000 --workers 4 [--hours 3]` starts a run; it checkpoints every 10 minutes and exits.
- `evobots resume runs/R12` continues a run.
- `evobots life` runs the ecology.
