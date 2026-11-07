# Round 32: housekeeping, MISO's non-commercial note, and "finish all of this"

Date: 2026-11-07. Areeb's instructions, in reply to the status list:
- on MISO's terms: "It states that the use of MISO data for non-commercial purposes is fine as long as credit is given";
- on repository housekeeping: "fix this on your own";
- on the Rates Factors file: "give me the link and I'll do it";
- on the remaining milestones: "finish all of this please".

## 1. CLAUDE.md retired; the specification moves to `docs/design_spec.md`

- On 2026-10-29 Areeb replaced `CLAUDE.md` on `main` with one line ("Outdated_File") and then deleted it, and removed its line from the README. `development` had edited it in round 31, so merging `main` gave a modify/delete conflict.
- **Resolved by keeping Areeb's deletion.** The design content moved to `docs/design_spec.md`, the file the briefing itself named as its successor (§0). Section numbers are unchanged, so every "§n" reference stays correct. The handoff-only parts (how to use the file, the first-session steps) were dropped; the revision history was kept.
- References in code, tests, tools and current docs now say `docs/design_spec.md`. Historical records (round docs, the decisions log, the change ledger) keep "CLAUDE.md" as written at the time; the spec's header says where that content now lives.

## 2. MISO's terms: the non-commercial note

- Recorded in `docs/data_sources.md` §4 in Areeb's words. The source text is still not in the project: the Terms of Use pasted in round 25 contain no commercial/non-commercial distinction, and round 27's search found such terms only for an unrelated UK company also called Miso.
- **What it changes:** private, non-commercial use of the already-downloaded data with credit, which was already the round-26 position. The README's acknowledgments now give the credit line explicitly.
- **What it doesn't change:** the separate clause "You agree not use any automated means … to access, monitor, or copy any part of this Website". Use terms and access terms are different questions, so **scripted MISO downloads stay off**. Nothing in M2–M9 needs them: paper trading reads files Areeb saves into `data/inbox/` (`docs/design_spec.md` §7.11, M9).

## 3. Repository housekeeping

| Item | Done |
|---|---|
| Round 31 on `main` | merged through a pull request |
| `main` and `development` | `main` merged into `development` (above) |
| Old `claude/...` branches | deleting them returns HTTP 403 from this session's GitHub access (round 29). Not worked around; Areeb deletes them under Branches on github.com |
| Public repository and Pages source | repository settings, which this session's tools can't change. Areeb: Settings → General → Danger zone → Change visibility; then Settings → Pages → Source: GitHub Actions |

## 4. Rates Factors file

Asked for a link. No direct URL could be confirmed: MISO's site refuses scripts, and a web search found no page with that title. The path given to Areeb: misoenergy.org → Markets and Operations → Settlements → Market Settlements → Related Documents → "Market Settlements Rates Factors". The likely page, `https://www.misoenergy.org/markets-and-operations/settlements/market-settlements/`, was **not checked**. Until the file arrives, fees and uplift stay labelled estimates (D3).

## 5. "Finish all of this"

Areeb asked for every remaining milestone. The pacing rule of round 23 (stop at the §2.4 check-ins) is set aside by this instruction: the work runs M2 → M9 with the ORFE track, committing each milestone with its round doc, and the check-in items are reported together at the end instead of one at a time.
