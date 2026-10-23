# Round 18: M0 continued: network opened, MISO rules researched

Date: 2026-10-23. Environment: Claude Code in a cloud container (same as round 17). Branch `claude/jolly-cannon-w2vfcu`, starting from round 17's commit.

## 1. What changed since round 17

- **Contact email received.** Stored in the git-ignored `config/local.toml` under `[network] contact_email` (`CLAUDE.md` §5.4). The committed template is `config/local.example.toml`. The email appears in no committed file.
- **The network policy now lets the data domains through.** Round 17 saw `CONNECT tunnel failed, response 403` for every data domain. Today every tunnel opened. Probe: `python tools/probe_domains.py` (one HEAD per domain; User-Agent `evobots/0.1 (research; environment probe; contact: …)`), obs.:

| Domain | Result | Note |
|---|---|---|
| `docs.misoenergy.org` | reachable | 404 at `/marketreports/` itself; files there return 200 (below) |
| `cdn.misoenergy.org` | reachable | 403 at the bare root from CloudFront (no index page); named documents return 200 |
| `www.misoenergy.org` | reachable, **refuses scripts** | 403 with a Cloudflare challenge (`server: cloudflare`, `chlray`) |
| `help.misoenergy.org` | reachable | 200 |
| `mesonet.agron.iastate.edu` | reachable | 200 |
| `www.eia.gov` | reachable | 503 to HEAD, 200 to GET |
| `api.eia.gov` | reachable | 403 at root (API needs a path) |
| `www.policyuncertainty.com` | reachable | 200 |
| `www.matteoiacoviello.com` | reachable | 200 |
| `thedocs.worldbank.org` | reachable | 200 |
| `oasis.caiso.com` | reachable | 200 |
| `www.ams.org` | reachable, **refuses scripts** | 403 with a Cloudflare challenge |
| `arxiv.org`, `export.arxiv.org` | reachable | 200 |
| `pypi.org`, `files.pythonhosted.org`, `github.com` | reachable | as in round 17 |

  The two Cloudflare-protected sites block non-browser clients on purpose. Following §5.4 rule 2, I didn't try to get around that. They matter for: MISO's rate notices, rates history file and BPM pages (`www.misoenergy.org`), and the Bailey et al. MinBTL paper (`www.ams.org`).

- **MISO's price server still publishes** (access risk, `CLAUDE.md` §6.5): on 2026-10-23, `20261020_da_expost_lmp.csv`, `20261018_rt_lmp_final.csv`, `202001_rt_lmp_final_csv.zip` and `200504_da_lmp_csv.zip` all answered 200 (obs., HEAD requests).

## 2. M0 research done this round

Full write-up with sources: [market_rules.md](../market_rules.md). Headlines:

1. **Bid deadline** is 10:30 a.m. EPT today, but was **11:00 a.m. EST** (noon clock time in summer) until 2016-11-05. A single 10:30 EPT decision time is safe for every year. → decision D1 below.
2. **Preliminary RT prices are not archived** (only the last ~3 days exist). The final-RT lag was 4 days today; the design's D−6 rule stays.
3. **Costs:** Schedule 17 + 24 ≈ $0.090/MWh (Oct 2026), charged on |net| MW per node-hour. RSG: DA RSG on net virtual demand per node; RT RSG (DDC) on net virtual supply **summed over all nodes**, at a market-wide hourly rate. So MISO nets positions, per asset owner. That answers the §20.6 [verify].
4. **RSG history has three eras:** none on virtual supply before 2008-11; high (whole volume as deviation) 2008-11 → 2011-03; much lower from 2011-04. A 2005–2025 backtest with today's fees would misstate 2008–2011. The rate values themselves need MISO's Rates Factors file → request R1.
5. **Collateral:** formula, $12 MPD floor and VMEW = 2 confirmed; $22,464 at full size confirmed. New: the Virtual MWh Limit counts **submitted** MWh, not cleared, and unpaid realised losses also count against credit.
6. **Eligibility:** Attachment L v56.0.0's virtual-trading text is unchanged in v57.0.0 (filed 2025-07). Minimum capitalization for a non-FTR trader is **$500k tangible net worth** (audited) or **$200k** financial security, half of it locked.
7. **Holidays:** the NAESB and PJM/NERC sources disagree about Sunday holidays. → decision D2.

## 3. Attachment L v56.0.0 vs v57.0.0 comparison

Run from `data/raw/rules/` after `tools/fetch_rule_documents.py` and `pdftotext -layout` on D2 and D3. Result on 2026-10-23: §IV.A identical; §III.B and the virtual exposure formula differ only in PDF glyph codes (bullet `•` vs ``, and spacing inside the formula image).

```python
import re, difflib
v56 = open("attachment_l_586302.txt").read()
v57 = open("er25_2845_707828.txt").read()
v57 = v57[v57.find("56.0.0, 57.0.0") - 200:]          # start of the Attachment L redline

def normalised(text):
    text = re.sub(r"(?m)^.*(ATTACHMENTS|Effective On:|FERC Electric Tariff|^MISO\s{5,}).*$", "", text)
    return re.sub(r"\s+", " ", text)

old_text, new_text = normalised(v56), normalised(v57)
for start, end in [("B. Demonstration of Appropriate Person Status", "D. "),
                   ("IV. ALLOCATION OF CREDIT LIMIT TO VIRTUAL", "B. Allocation of Credit Limit to FTR"),
                   ("3) Virtual Transaction Potential Exposure", "4) Congestion and Losses Potential")]:
    old_section = old_text[old_text.find(start):]; old_section = old_section[:old_section.find(end, len(start))]
    new_section = new_text[new_text.find(start):]; new_section = new_section[:new_section.find(end, len(start))]
    matcher = difflib.SequenceMatcher(None, old_section, new_section, autojunk=False)
    print(start, [operation for operation in matcher.get_opcodes() if operation[0] != "equal"])
```

## 4. Decisions needed (Areeb)

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | Decision time for point-in-time data | **A** 10:30 EPT on D−1 for every year; **B** era-correct deadline (11:00 EST before 2016-11-05) | **A**: never later than the real deadline, one rule, one test |
| D2 | `holiday` flag when a NERC holiday falls on a Sunday | **A** flag the date and the following Monday; **B** follow the newest NERC list exactly once found | **A** |
| D3 | Fees before the Rates Factors file arrives | **A** build M3 with the cost model in `market_rules.md` §3.2 and placeholder rates, clearly flagged; **B** wait for the file | **A**; M3 is several milestones away anyway |

And one request:

| # | Request | Why |
|---|---|---|
| R1 | In a browser, open misoenergy.org → Markets and Operations → Settlements → Market Settlements → Related Documents, download the **Market Settlements Rates Factors** file, and put it in `data/inbox/` | Schedule 17/24 and RSG (DDC, CMC, DA RSG) rate history 2005–2026. Cloudflare blocks scripts on that site |
| R2 (optional) | From the same site's Business Practices Manuals page: BPM-002 and BPM-009 | current price caps and block count; IMM virtual volume limits |

## 5. Individual's fixed yearly costs (first estimate)

| Item | Amount | Status |
|---|---|---|
| MISO annual participation fee | none found in Attachment L, the virtual-trading guide or the settlement guide | [verify] against MISO's registration pages |
| Schedule 17 + 24 administration | $0.0902/MWh (Oct 2026). At full Stage A size (936 MWh/day) that is **$22.2k/year at the 72.1 % hub clearing rate**, $30.8k if everything cleared | computed from [verify] rates; this is a **per-MWh fee**, modelled in `fees_usd`, not a fixed cost |
| Annual audited financial statements | required for the $500k tangible-net-worth route (Attachment L §III.C.1) | **cost not measured**: assumption |
| Accounting, legal, registration, computing, data | data is free (keyless sources) | assumption |

Arithmetic: 936 × 0.721 × 365 = 246,322 MWh/year × $0.0902 = $22,218; 936 × 365 × $0.0902 = $30,816.

**Proposal:** keep the $50k/year fixed-cost assumption (`CLAUDE.md` §10.1) as is; it now has to cover audit, accounting and legal only, since MISO's own charges are per MWh and sit in the fee model. I found no hard number to replace it.

## 6. Also added this round

- `tools/probe_domains.py`: the domain probe as a script (round 17 recorded results only).
- `tools/probe_rt_archive.py`: final-RT lag and preliminary-RT depth; reproduced the hand probe exactly.
- `tools/fetch_rule_documents.py`: downloads the 13 documents behind `market_rules.md` into the git-ignored `data/raw/rules/` and checks SHA-256.
- `docs/glossary.md`: the §19 seed plus 14 market terms from this round.
- `tests/test_doc_links.py`: internal-link checker for every tracked `*.md` (files and `#heading` anchors; external links not fetched), with a self-test. Suite: 7 passed, sockets disabled. ruff: clean.

## 7. M0 status

| M0 task | Status |
|---|---|
| Run the 40 tests | **blocked**: project files still missing (round 17 §1) |
| Resolve the [verify] list; `market_rules.md` | **draft done**; open items in `market_rules.md` §7, D1–D3, R1–R2 |
| Redistribution terms in `data_sources.md` | **now unblocked** (domains reachable); next |
| `maths.md` | blocked on `capital_sizing.md` and `sizing.py` |
| Standards tooling | link checker done; `test_naming.py`, `benchmarks/run.py` need code |
| Docs skeleton, glossary, `config_reference.md` | glossary done; `config_reference.md` needs `capital.py` |
| Naming pass; explorer fix and browser test | blocked on project files |
| Record decisions; mark $1.5M final | blocked on `decisions_log.md`, `design_spec.md` |
| O0 DC-OPF explanation | not started |

## 8. Measured vs assumed

**Measured (obs.):** the domain probe in §1; MISO server files present today; everything marked (obs.) in `market_rules.md`; the v56/v57 comparison in §3; test and lint results in §6.

**Assumed:** that the Cloudflare 403s are the sites' bot protection, not an outage (the response headers say Cloudflare challenge); the Schedule 17/24 rates (search-index quotes); everything listed under "Assumed or unverified" in `market_rules.md` §9; the cost items marked assumption in §5.
