# Round 17: M0 kickoff (first Claude Code session)

Date: 2026-10-23. Environment: Claude Code in a **cloud container**, not Areeb's laptop.

## 1. Stocktake of the folder (CLAUDE.md §4)

The repository (`areebnaumanmir-lab/Evobots-Programming-Project`) held only a one-line `README.md` (obs.: `git ls-tree -r origin/main`; there are no other branches with content).

| §4 item | Status |
|---|---|
| `CLAUDE.md` | **added this round** (the handoff prompt, verbatim) |
| `pyproject.toml`, `uv.lock` | **added this round** (tooling only; see §4 below) |
| `configs/10_miso_hubs.toml` | missing |
| `src/evobots/` (`__init__.py`, `cli.py`, `sizing.py`, `storms.py`, `config/`) | missing |
| `tests/` (the 40 tests) | missing |
| `tools/` (`build_hub_sample.py`, `fetch_2015_2018.py`, `capital_analysis.py`, `capital_explorer.html`) | missing |
| `docs/` (design spec, decisions log, capital sizing, the other docs, rounds 3–8, plans) | missing |
| `docs/data/` CSVs and figures | missing |
| `evobots_stage_a_capital.zip` | not provided |

Nothing unexpected was found. Following §4, none of the missing files has been recreated from the prompt.

**Consequence:** M0 step zero (run the 40 tests) cannot run yet. The same goes for the naming pass, the explorer fix and its Playwright test, and `maths.md` (which links formulas to existing functions and tests).

## 2. Environment (obs.)

| Item | Value | Command |
|---|---|---|
| OS | Ubuntu 24.04.5 LTS (Linux), cloud container | `cat /etc/os-release` |
| Python | 3.13.17 | `python3 --version` |
| uv | 0.11.32 | `uv --version` |
| git | 2.43.0 | `git --version` |
| CPU cores | 4 | `nproc` |
| RAM | 15 GiB total, 14 GiB free | `free -h` |
| GPU | none (`nvidia-smi` absent) | |
| Disk | per-session allowance; 31 GB shown free | `df -h` |

The container has 4 cores, not the laptop's 20. Benchmarks recorded here are **not** comparable with the §14.3 targets, which assume 20 cores. Each benchmark row will record its machine.

## 3. Data-domain probe (CLAUDE.md §5.4, §7.9)

One HEAD request per domain, User-Agent `evobots/0.1 (research; environment probe)`. "Blocked" means the environment's egress proxy refused the tunnel (`CONNECT tunnel failed, response 403`). The site itself was never reached.

| Domain | Result | Needed for |
|---|---|---|
| `docs.misoenergy.org` | **blocked** | core prices (M1), cleared bids |
| `cdn.misoenergy.org` | **blocked** | M0 rule documents (Attachment L, fees, RSG, BPMs) |
| `www.misoenergy.org` | **blocked** | M0 rules, access-risk pages |
| `help.misoenergy.org` | **blocked** | Data Exchange FAQ |
| `mesonet.agron.iastate.edu` | **blocked** | NWS forecasts (input), ASOS (reporting) |
| `www.eia.gov` | **blocked** | Henry Hub (input), EIA-860M (input), WTI (reporting) |
| `api.eia.gov` | **blocked** | optional bulk files |
| `www.policyuncertainty.com` | **blocked** | EPU (input) |
| `www.matteoiacoviello.com` | **blocked** | GPR (reporting) |
| `thedocs.worldbank.org` | **blocked** | Pink Sheet (reporting) |
| `oasis.caiso.com` | **blocked** | CAISO adapter (later) |
| `www.ams.org` | **blocked** | MinBTL paper check |
| `arxiv.org`, `export.arxiv.org` | **blocked** | literature checks, 1802.03010 (O2) |
| `pypi.org` | reachable (HTTP 200) | packages |
| `files.pythonhosted.org` | reachable (404 at root, as expected) | packages |
| `github.com` | reachable (400 to a bare HEAD) | packages |

Following §5.4 rule 2, nothing was retried through other tools.

## 4. Decisions (Areeb, this round; answers to §17.1)

| # | Question | Decision |
|---|---|---|
| 1 | UI editing language | **A**: FastAPI + Jinja2 + one `theme.css`, no build step |
| 2 | Offline scope | **(a)** offline once installed; first install may download packages (round-1 decision stands) |
| 3 | Single-file deliverables | "The exported bots should work independently of source code." Exported bots are **standalone files that do not import `evobots`** (standard library only), with the equivalence test from §14.6. Whether the engine also ships as a `.pyz` was not answered. It is not needed before M9 and will be asked then. |
| 4 | Performance targets | **accepted as proposed** (§14.3) |

These rows go into `docs/decisions_log.md` once that file is in the repository. It is one of the missing files, so it hasn't been recreated here.

## 5. Tooling added (M0, independent of the missing files)

- `CLAUDE.md`: the briefing, so every session reads it.
- `.gitignore`: raw data, the store, `data/holdout/`, `config/local.toml`, `runs/` and caches (§5.3).
- `pyproject.toml` and `uv.lock`: Python ≥ 3.13; hatchling with a `src/evobots` layout; dev group `pytest`, `pytest-socket` and `ruff`. pytest runs with sockets disabled except localhost, plus doctests (§14.4). ruff runs with pep8-naming, docstring rules (Google style) and import order (§14.1–14.2). Runtime dependencies are only `numpy` for now. They are added milestone by milestone, with licences recorded in `docs/dependencies.md`.

## 6. M0 plan and what each step waits on

| M0 task | Blocked on |
|---|---|
| Run the 40 tests as they are | project files |
| Naming pass (`cli.py`, `capital.py`, `sizing.py`, explorer) | project files |
| Fix `capital_explorer.html`; Playwright console-error test | project files |
| `test_naming.py`, `naming_allowlist.txt`, link checker, `benchmarks/run.py` | project files (they need code to check) |
| Resolve the [verify] list; write `market_rules.md` | `cdn.misoenergy.org`, `www.misoenergy.org`, `docs.misoenergy.org` (server probe for preliminary RT) |
| Redistribution terms in `data_sources.md` | every data domain above |
| `maths.md` (formula ↔ function ↔ test) | project files (`capital_sizing.md`, `sizing.py`) |
| Docs skeleton, glossary seed, `config_reference.md` | `config_reference.md` needs `capital.py`; the glossary seed can be written now |
| Record decisions, mark $1.5M final in the spec | `decisions_log.md`, `design_spec.md` |
| O0 DC-OPF explanation | nothing in principle; it needs the `src/evobots` package, which is missing |

## 7. Measured vs assumed

**Measured (obs.):** repository contents; Python, uv, git, cores, RAM, GPU, OS; the domain probe results in §3; that `uv lock` resolves numpy 2.5.4, pytest 9.1.1, pytest-socket 0.8.1 and ruff 0.17.2.

**Assumed:** that the missing files exist on Areeb's side as described in §4 of the briefing; that the egress block is this environment's network policy rather than the sites being down. The proxy returned 403 at CONNECT for all of them, while PyPI and GitHub succeeded.
