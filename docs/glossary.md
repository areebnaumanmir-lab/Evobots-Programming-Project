# Glossary

The project's dictionary: one word per idea (`CLAUDE.md` §14.1). Code, docs and the app use these terms with these meanings. Seeded from `CLAUDE.md` §19; terms from [market_rules.md](market_rules.md) added in round 18.

## Market

| Term | Meaning |
|---|---|
| ISO | Independent System Operator; runs the grid and the electricity markets (MISO, CAISO, PJM, NYISO, ERCOT, ISO-NE) |
| MISO | Midcontinent Independent System Operator, the US Midwest and South market this project trades |
| DA / RT | day-ahead and real-time markets |
| LMP | locational marginal price, $/MWh, at one location and hour; components energy, congestion (MCC) and loss (MLC) |
| ex-ante / ex-post LMP | two DA price versions MISO publishes: ex-ante is the price that clears bids; ex-post is the price that settles them |
| CP node | commercial pricing node: a location where MISO publishes an LMP and accepts bids (generator, load zone, interface or hub) |
| dead node | a CP node cut off from the grid by an outage; it still has a price, but no virtual can clear there |
| hub | a trading hub: a liquid average of many nodes (8 in MISO today) |
| operating day | the day D the power flows; bids are placed on D−1 |
| EPT / EST | Eastern Prevailing Time (local clock time, shifts with daylight saving) / Eastern Standard Time (never shifts) |
| hub-hour / location-hour | one hour at one hub or location: the unit a bid is placed on |
| virtual bid, INC, DEC | financial position in DA, reversed in RT; INC = virtual supply, earns DA − RT; DEC = virtual demand, earns RT − DA |
| spread | DA − RT |
| cleared | the bid's limit price was met, so it was accepted in DA |
| asset owner | the account a participant's positions and charges are settled under; one bot is one asset owner in the simulator |
| net virtual position | DEC MW minus INC MW, per node or summed over nodes; several MISO charges use it instead of gross MW |
| Schedule 17, Schedule 24 | MISO's per-MWh administration charges (market administration; local balancing authority cost recovery) |
| RSG | Revenue Sufficiency Guarantee: an uplift cost that pays generators committed outside the market, allocated partly to virtuals |
| DDC, CMC, VLR | the three parts of real-time RSG first pass: Day-Ahead Deviation and Headroom Charge (market-wide), Constraint Management Charge, Voltage and Local Reliability charge (both local) |
| MPD, VMEW | MISO credit terms: marginal price differential ($/MWh, ≥ $12) and a 2-day exposure window |
| Virtual MWh Limit | the daily cap on *submitted* virtual MWh a participant chooses; collateral is set from it |
| appropriate person | MISO eligibility status (Attachment L §III.B), e.g. net worth > $1M or total assets > $5M |
| minimum capitalization | a separate MISO test (Attachment L §III.C): for non-FTR participants, tangible net worth ≥ $500k, total assets ≥ $5M, or $200k of financial security |
| FTR | financial transmission right: a contract paying congestion price differences; not traded by evobots |
| IMM | Independent Market Monitor (Potomac Economics for MISO) |

## Project

| Term | Meaning |
|---|---|
| trader (bot) | one evolved strategy: genome + generated source code + life (`CLAUDE.md` §9.1) |
| genome | the trader's slot trees and numeric genes; what evolution changes |
| trader id / genome id / behaviour id | birth identity (`R12-184213`) / hash of the genes / hash of the bids on a reference window (§9.4) |
| training window | the 5 years of history a trader is scored on; it rolls forward a year at a time (§11) |
| operator | a way of making a child: subtree, point, hoist, size-fair crossover, constant or category mutation (§9.6) |
| founder | a hand-written starting trader with a stated reason (§9.5) |
| lineage, generation | a trader's ancestors and descendants; generation = lineage depth (§9.4) |
| selection pressure | how strongly fitness raises a trader's share of offspring (§11.2) |
| out of money | can't post collateral for the smallest bid: the default death (§10.1) |
| ruin floor (capital floor) | an optional wealth level at which a career ends; off by default since round 19 |
| drawdown limit | an optional stop after a given fall from the trader's peak equity |
| career | the rules under which a bot stops trading (L0 out of money by default; L1–L5 optional) |
| best bot | highest out-of-sample fitness among traders passing the deployment gates (§11.4) |
| Life mode | the market-time ecology: traders live, reproduce and die day by day through history (§11.3) |
| elite, niche | the best bot in one cell of the MAP-Elites map, and that cell |
| hold-out | the sealed 12 months, scored once per run |
| (obs.) / [verify] | observed in this project / not yet checked |

## Operations research and finance

| Term | Meaning |
|---|---|
| VaR, CVaR / expected shortfall | the loss exceeded with probability 1 − α, and the average loss beyond it |
| SAA | sample average approximation: replace an expectation by an average over sampled scenarios, then optimize |
| perfect-foresight bound | the profit an optimizer earns knowing future prices; an upper bound, never a strategy |
| policy | a rule mapping what is known now to a decision |
| state of charge (SoC) | energy stored in a battery, MWh |
| shadow price / dual | how much the optimal objective changes per unit relaxation of a constraint; an LMP is the shadow price of power balance at a location |
| DC-OPF | DC optimal power flow: the linearised grid-dispatch problem whose duals give LMPs |
| PTDF | power transfer distribution factor: the share of 1 MW, injected at a bus and withdrawn at the reference bus, that flows on a line ([maths.md](maths.md) §2.1) |
| reference bus | the bus whose price is the energy component of every LMP; the split of an LMP into energy and congestion depends on it, the LMP itself does not |
| MEC, MCC, MLC | the energy, congestion and loss components of an LMP, as MISO publishes them; LMP = MEC + MCC + MLC |
| ARL | average run length: expected time before a sequential test (e.g. CUSUM) raises an alarm |
| Pareto front | the set of solutions no other solution beats on every objective |
