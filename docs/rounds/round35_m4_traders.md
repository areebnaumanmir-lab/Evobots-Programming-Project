# Round 35: M4, the trader as a typed program

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- `src/evobots/bots/grammar.py`: the trader language. It has typed, unit-checked nodes (feature, constant, `+ − × ÷ min max`, `abs`, `if`, `> <`, `and or not`, `in {…}`, the holiday flag); a display form, a code form that parses back, canonical JSON, and vectorised evaluation with a sub-expression cache. A missing input stays missing through every node, so `not` of a missing comparison is missing, never true.
- `src/evobots/bots/trader.py`: the genome. It holds three slot trees plus eight numeric genes (side thresholds, price offset, size fraction, size scale, daily cap, pause rule), its full-size bids as a `Decisions` matrix for the simulator, genome ids (SHA-256 of canonical JSON), behaviour ids (hash of bids on a window) and two-word names.
- `src/evobots/bots/random_trees.py`: PTC2 with types and units, and constant ranges from the store's measured quantiles.
- `src/evobots/bots/variation.py`: the operators. Subtree, point (with category-set add/remove), hoist, size-fair crossover, constant steps of 2/10/30 % with iso+line-DD on the numeric genes, and the adaptive operator bandit with a 5 % floor.
- `src/evobots/bots/founders.py`: the seven founders of §9.5, each with its reason.
- `src/evobots/bots/source.py`: the standalone, standard-library trader file. Its header holds the plain-English rules and the inputs; it includes a `--scale` option; it parses back into the genome (code ⇄ genome, round 20); and it can read and write input CSVs.

## Done-when check (design spec §16, M4)
- **JSON round-trips exactly:** for every founder and 300+ random and varied genomes (`tests/test_traders.py`).
- **Every trader's generated file gives exactly the engine's bids:** side, limit and MW compared with `==` on random days through the CSV the file reads, at full size and at a random position scale (over 1,000 bids per run).
- **Planted-signal test:** it needs the search, so it runs with M6 (round 37) on the same operators.
- **Traders and Trader pages, View code, "What did it see?":** built with the app (`source.input_rows` gives the panel its data).

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| Missing inside logic | strict: any missing operand makes `and`, `or`, `not` missing | §8 "missing makes any comparison false … the bot doesn't trade on that input"; Kleene logic would let `not missing` trade |
| Size slot | cap × size fraction × min(1, \|score\| ÷ size scale) | §9.2's "2 MW × min(1, \|score\|/10)" with the evolved scale; the hard cap stays outside the genome |
| Daily cap gene | a fraction of the full-size footprint | stays meaningful at every stage (8 hubs or all locations) |
| Comparison thresholds | PTC2 makes a comparison's right side a constant 80 % of the time | thresholds are the common, readable case |
| Names | 64 adjectives × 64 animals from SHA-256 of the trader id | memory aid only; the id is always shown beside it |

## Measured vs assumed
- **Measured:** round trips and equivalence on the test populations.
- **Assumed:** the function weights of PTC2 and the 80 % threshold chance (search parameters, not facts).
