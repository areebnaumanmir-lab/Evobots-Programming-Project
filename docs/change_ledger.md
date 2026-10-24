# Change ledger

One row per change, newest first (`CLAUDE.md` §14.2). Every commit adds a row; `tests/test_change_ledger.py` checks that every round doc in `docs/rounds/` is listed here.

Columns:
- **Date:** when the change was made.
- **Round:** the round doc that explains it.
- **Commit:** the commit that made it ("this commit" until the hash is known, then filled in at the next change).
- **What changed:** the change itself.
- **Why:** the reason.
- **Files:** what was touched.
- **Decision:** the decision it records or still needs.

| Date | Round | Commit | What changed | Why | Files | Decision |
|---|---|---|---|---|---|---|
| 2026-10-24 | [round 21](rounds/round21_reconciliation.md) | this commit | Decisions log (rounds 1–16) and `capital_sizing.md` with three CSVs added; rounds 17–21 appended to the log; Claude Science's calibration reproduced exactly from the archive (176/176 hub statistics, 12/12 benchmark numbers, the §4b trailing-p99 table and breach rates); §4b figure redrawn; `design_rationale.md` Part C rewritten from the log | Areeb uploaded the files | `docs/decisions_log.md`, `docs/capital_sizing.md`, `docs/data/*.csv`, `docs/data/figures/*`, `docs/design_rationale.md`, `tools/check_against_claude_science.py`, `CLAUDE.md`, `pyproject.toml` | Resolved: `credit_share` meaning. No conflicts found |
| 2026-10-24 | [round 20](rounds/round20_literature_data_style.md) | `3503956` | Literature review and living rationale (`design_rationale.md`); 77 references checked; decisions changed (5-year window, elite re-evaluation, ids, PTC2, size-fair crossover, iso+line-DD, bandit operators, neutral skip, code round trip); round-18/19 choices decided under delegation; full MISO DA/RT archive downloaded and parsed; manifest; coverage report; visual style from Areeb's reference, theme tokens and a preview on real data | Areeb's round-20 instructions | `CLAUDE.md`, `docs/design_rationale.md`, `docs/references.*`, `docs/data/references_checked.json`, `docs/data_coverage.md`, `docs/design/*`, `data/manifest.toml`, `tools/*.py`, `pyproject.toml` | Delegated: R19-1…6, D1–D3. Open: R1 Rates Factors file |
| 2026-10-23 | [round 19](rounds/round19_prompt_review.md) | `6890472` | Briefing reviewed against 20 questions and revised: trader as organism with generated source code; ids, names, lineage; founders; mutation operators with sources; out-of-money death by default; reproduction and selection pressure; compute vs market time and Life mode; best bot, Refine, sealed test in practice, grid map; setting badges; data and input status; documentation and ledger rules; UI separation and white visual style. Ledger and ledger test started. | Areeb's 20 review questions | `CLAUDE.md`, `docs/rounds/round19_prompt_review.md`, `docs/change_ledger.md`, `docs/glossary.md`, `tests/test_change_ledger.py` | Decided: out-of-money death, buttons, UI separation, ledger, documentation, white style. Open: R19-1 … R19-7 |
| 2026-10-23 | [round 18](rounds/round18_m0_market_rules.md) | `bfd9f50` | MISO market rules researched from 13 documents; probe and fetch scripts; glossary; doc link checker; local config template with the contact email kept out of git | M0 [verify] list; network policy now allowed the data domains | `docs/market_rules.md`, `docs/rounds/round18_m0_market_rules.md`, `docs/glossary.md`, `tools/*.py`, `tests/test_doc_links.py`, `config/local.example.toml` | Open: D1–D3, R1–R2 |
| 2026-10-23 | [round 17](rounds/round17_m0_kickoff.md) | `1085133` | Briefing saved as `CLAUDE.md`; stocktake; environment and domain probe; tooling config (`pyproject.toml`, `uv.lock`, `.gitignore`) | M0 kickoff | `CLAUDE.md`, `docs/rounds/round17_m0_kickoff.md`, `pyproject.toml`, `uv.lock`, `.gitignore` | Decided: the four §17.1 questions |
