# MISO market rules for virtual trading

Explanation doc (Diátaxis). It answers the M0 [verify] list in `docs/design_spec.md` §16 from MISO's own documents, says what each rule means for the simulator, and lists what is still open.

Provenance markers (`docs/design_spec.md` §2.2):
- **(obs. Dn)**: read in document Dn, downloaded on 2026-10-23 and listed with its URL and SHA-256 in §8. `tools/fetch_rule_documents.py` downloads them again and checks the hashes.
- **(obs. probe)**: measured against MISO's server with the named script in `tools/`.
- **[verify]**: not yet read in a primary source. Each one says what would settle it.

Status: draft for the end-of-M0 check-in (round 18). Times are Eastern Prevailing Time (EPT, local clock time in the Eastern zone) unless marked EST.

---

## 1. What a virtual bid is and how it settles

- A **virtual demand bid (DEC)** buys MW in the day-ahead (DA) market at a commercial pricing node (CP node); the same MW are automatically sold back in real time (RT) at that node's RT price. A **virtual supply offer (INC)** is the mirror image. No energy flows. (obs. D1, FAQ 1, 15, 16)
- Settlement uses the **DA ex-post LMP** and the RT LMP at the node: a cleared DEC of q MW earns q × (RT − DA). (obs. D1, "Settlements" and FAQ 1) This is the price series the brief already uses (`{date}_da_expost_lmp.csv`). The cleared-bids report carries the DA **ex-ante** LMP, which is the price used to *clear* the bid; the two differ slightly (`docs/design_spec.md` §6.2).
- **Clearing:** a block clears when its limit price is met (DEC: price ≥ DA LMP; INC: price ≤ DA LMP). Blocks are steps, never slopes; a block **clears partially only when the LMP equals its price** (it is marginal). (obs. D1, FAQ 12, 13) This matches the 0.16 % partial fills measured in Claude Science.
- **Dead nodes:** a node islanded by an outage still gets a price, but no virtual can clear there. (obs. D1, "Dead Nodes") This is a likely cause of part of the 0.5 % of bid-hours the price rule mispredicts (`docs/design_spec.md` §6.2); not checked.
- **There is no counterparty.** MISO is revenue neutral: virtual losses fund other participants' credits. (obs. D1, FAQ 5, 18)

### Bid format

| Rule | Value | Source |
|---|---|---|
| Minimum size and step | 0.1 MW | obs. D1, FAQ 11 |
| Locations | any CP node: generator, load zone, interface or hub (about 2,200) | obs. D1, FAQ 7 |
| Price range, INC offer | −$500 to $1,000/MWh | obs. D1, p. 4 |
| Price range, DEC bid | −$500 to $2,000/MWh | obs. D1, p. 4 |
| Blocks per bid | up to 9 MW/price blocks (p. 4); FAQ 8 says "up to 10 price/quantity pairs per hour per CP node" | obs. D1; the two statements in D1 disagree. **Round 27:** the cleared-bids report carries 9 price/MW pairs, and bids use all 9 (1,267 bids on 2025-01-15; obs.). Whether MISO accepts a 10th that the report drops can't be told from the data. Our traders bid one block, so it doesn't matter |
| Earliest submission | 7 days before the operating day | obs. D1, FAQ 6 |
| Changing one hour | a resubmission for one hour nulls the other 23; resubmit all hours | obs. D1, FAQ 10 |
| Volume limits | "subject to credit limits and IMM volume limits" | obs. D1, p. 4. **Round 27:** no MW volume limit was found. The IMM's 2024 State of the Market report describes a **screen**: price-insensitive virtual transactions that cause day-ahead/real-time congestion divergence ("Screened Transactions") "raise potential manipulation" concerns (obs., pp. 32–33). Our cap (≤ 5 MW per hub-hour) is below the median single participant's 8 MW. But a trader bidding with no effective limit price is price-insensitive: the report card should flag that behaviour |

D1 dates from August 2022 (PDF metadata). The price ranges are from that date; MISO may have changed offer caps since (for example the $1,000 → $2,000 range for demand bids). **Round 27:** the $1,000/MWh soft and $2,000/MWh hard energy offer caps are confirmed: the IMM's 2023 report, footnote 40, and BPM-002-r23 §5 ("Energy Offer Hard Price Cap ($2,000)", effective 2022-09-30, from a copy filed with the Kentucky PSC). Caps specific to virtual bids were not found. **Decision for M3:** the simulator never rejects a bid for its limit price. A limit beyond any cap just means "clear at any price", so the caps can't change results.

**For the simulator:** bots never come near these price limits (their limit price is `da_last` ± an offset), so the caps only need a validation check. The 0.1 MW step is already in the sizing rule.

---

## 2. Timeline: what a bot can know when it decides

### 2.1 The DA bid deadline changed in 2016

| Period | DA market closes | DA results posted | Source |
|---|---|---|---|
| 2005-04 → 2016-11-05 | **11:00 a.m. EST, fixed**: 11:00 clock time in winter, **12:00 noon** clock time during daylight saving time | 3:00 p.m. EST (4:00 p.m. EPT in summer) | obs. D9, ¶13 (FERC order of 2015-12-17, describing the rule then in force). That 11:00 EST already held in 2005–2007 rests on two second-hand sources: a 2007 ATC customer notice found by search says "1100 EST", and a 2014 FERC-related table found by search gives MISO bids due at 10:00 a.m. Central (round 27). Moot under decision D1 (the bot decides at 10:30 EPT, never later) |
| 2016-11-05 → today | **10:30 a.m. EPT**, year-round (9:30 a.m. Central) | 1:30 p.m. EPT | Current rule: obs. D12 (MISO help article KA-01129) and D1 FAQ 6. Change date 2016-11-05 (for operating day 2016-11-06): from a MISO notice hosted on `www.oasis.oati.com`, seen only through a search summary; the host returned HTTP 503 three times. **Round 27:** BPM-002-r19 (effective 2018-10-15; a copy filed with the Missouri PSC) confirms "Virtual Supply Offers and Virtual Demand Bids … OD-1 @ 1030 EPT", with DA results posted at 13:30 EPT and **DA ex-post LMPs at 16:30 EPT** (Exhibit 7-1). The exact 2016 date stays second-hand; moot under D1 |

Also from D12: rebid period closes 2:30 p.m. EPT; reliability assessment commitment (RAC) results 6:00 p.m. EPT.

**For the point-in-time design (`visible()`)**, two options:

- **A (recommended): one decision time, 10:30 a.m. EPT on D−1, for every year.** It is never later than the real deadline in any era (11:00 or 12:00 EPT before 2016), so it can't leak information. Cost: before 2016 a bot sees a weather forecast issued up to 1.5 h earlier than a real trader could have used. NWS PFM issues come a few times a day, so this rarely changes which issue is "latest" [verify on the parsed table in M1].
- **B: the era-correct deadline.** More realistic before 2016, but adds a date-dependent rule that every feature and test must respect.

This is a design point for Areeb (§7).

### 2.2 RT prices: final files only, 4–5 days late

Measured on 2026-10-23 with `tools/probe_rt_archive.py` (obs. probe):

| File | Newest operating day on the server | Oldest |
|---|---|---|
| `{date}_rt_lmp_final.csv` | 2026-10-19, so a **4-day** lag at the time of the probe (about 19:00 UTC) | 2005 (monthly zips; `docs/design_spec.md` §7.3) |
| `{date}_rt_lmp_prelim.csv` | 2026-10-22 | **2026-10-20**: preliminary files exist only for the few days whose final file isn't out yet |

- Preliminary RT prices are **not archived**. No preliminary file exists for 2005-04-01, 2010-06-01, 2015-03-01, 2020-01-01, 2023-01-01 or any day from 2025-01-01 to 2026-10-19 (binary search). So the [verify] in `docs/design_spec.md` §6.4 is settled: **history can't use preliminary RT**, and the lag stays.
- Claude Science saw a 5-day lag on 2026-09-26; today's probe saw 4 days. The design's rule (on decision day D−1 the newest day with known P&L is **D−6**) stays safe against both.
- Paper-live mode (M9) could use preliminary RT for yesterday, but only going forward and only in reporting, since the bots were trained without it.
- **Cleared bids are published about 90 days late** (obs., round 23: on 2026-10-24 the newest `{date}_bids_cb.zip` was 2026-07-25; 2026-07-31 was a 404; the first file is 2023-01-01). Anything computed from them, such as hub liquidity medians or the O9 price-impact estimate, may use only days at least ~90 days before the decision, if it is ever made point-in-time.

### 2.3 Settlement and cash timing

- First settlement statement 7 days after the operating day ("S7"); invoices are posted weekly, on Tuesday afternoons. (obs. D1, "Settlements")
- Credit exposure includes virtual charges that are settled but not yet invoiced or paid (§4.1). So a loss reduces available credit **immediately**, not only when invoiced.

**For the simulator:** mark equity daily (as already decided). Cash timing doesn't change daily equity, so the weekly invoice cycle needs no model beyond the credit check in §4.

---

## 3. Costs charged to virtual trades

Four charges apply to a cleared virtual. (obs. D1 pp. 6–8; formulas obs. D5)

| Charge | Who pays | Volume it is charged on | Rate |
|---|---|---|---|
| **Schedule 17** market administration | all cleared virtuals | **\|net cleared virtual MWh\| per CP node per hour** for the asset owner: bids and offers at the same node net first (`DA_VSCHD_VOL = Σ ABS(DA_VSCHD)`, obs. D5 §B.4) | monthly; **$0.0746/MWh in October 2026**; $0.0852 (May 2026), $0.0817 (June 2026), $0.0824 (August 2025), $0.079 (December 2025). **[verify]**: these come from MISO's monthly rate notices as quoted by a search index. The notice pages refuse non-browser clients (Cloudflare). In round 27 the search index again showed MISO's own pages ("[MISO] Settlements - Energy Market Rates for May / June / October 2026") with the same values: still second-hand, but consistent |
| **Schedule 24** local balancing authority cost recovery | all cleared virtuals | same volume as Schedule 17 (`DA_S24_ADMIN_VOL` includes `DA_VSCHD_VOL`, obs. D5) | **$0.0156/MWh in October 2026** [verify, same source] |
| **DA RSG distribution** (`DA_RSG_DIST`) | net virtual **demand** | net cleared virtual demand **per node** per hour: 100 MW DEC + 50 MW INC at one hub pays on 50 MW; 50 DEC + 100 INC pays on 0 (obs. D1, FAQ 19) | daily/hourly market rate [verify] |
| **RT RSG first pass** (`RT_RSG_DIST1`) | net virtual **supply** | its main part, the Day-Ahead Deviation and Headroom Charge (DDC), is charged on the asset owner's hourly deviation volume, whose virtual term is the **net cleared virtual supply summed over all nodes** (`DDC_NDL_VIRT_VOL`); the total is floored at 0 (obs. D5 §D.14.6). The IMM states the same: "RSG or … DDC to virtual participants are assessed to net virtual supply, so participants can avoid such charges by clearing equal amounts of supply and demand" (obs. D6 and D7) | hourly market-wide **DDC rate** = DDC credits ÷ max(market deviation volume + headroom, committed capacity volume) (obs. D5). Plus two location-specific parts: the **Constraint Management Charge (CMC)** on deviations that load a constraint a RAC commitment relieves, and the **Voltage and Local Reliability (VLR)** charge (obs. D5 §D.14; D1 p. 7: "both virtual bids and offers are potentially subject to the RT RSG Constraint Management Charge") |

Sign check: in MISO statements seller volumes are negative and `DDC_NDL_VIRT_VOL = (DA_VSCHD_seller + DA_VSCHD_buyer) × −1`, so net supply gives a positive deviation. That reading matches the IMM's wording above; the sign convention itself is [verify] in the BPM-005 glossary.

### 3.1 RSG history matters for a 2005–2025 backtest

From Birge, Hortaçsu, Mercadal & Pavlin (2017), *Limits to Arbitrage in Electricity Markets: A Case Study of MISO*, MIT CEEPR WP 2017-003 (obs. D8, pp. 13–15), and the IMM (obs. D6, Figure A61 text):

| Period | RSG on virtual supply |
|---|---|
| 2005-04 → 2008-11 | **none**: "When the MISO market first opened in 2005, virtual transactions were not subject to RSG charges." |
| 2008-11 → 2011-03 | **high**: FERC ruled in November 2008 that virtual supply must pay; "the whole volume sold in the day-ahead market counted as a deviation, and thus these charges acted like a per unit transaction cost." Retroactive resettlement back to April 2006 started in January 2009 and was then abandoned by FERC. D8 reports the DA premium **net of RSG** was negative for virtual supply in 2010-01 → 2011-03. |
| 2011-04 → today | **much lower**: "the calculation of the charges was modified in a way that significantly lowered them for virtual transactions" (D8); RSG split into constraint-related (CMC) and market-wide (DDC, Pass 2) parts (D6). Until March 2014 too much constraint-related RSG was charged under DDC (D6). |

D8's summary table gives an RSG first-pass rate (`RSG1`) with mean **$1.8/MWh**, standard deviation 2.3, maximum 21.0, over 10,920 observations, from data covering 2008–2012; the table doesn't say which months the RSG series spans (10,920 hours ≈ 455 days). The CMC and DDC rows (means 2.2 and 0.9, N 10,470,096) are node-hour level. These are the only RSG *numbers* found so far.

**Missing:** the actual hourly or monthly DDC, CMC and DA RSG rates for 2005–2026. MISO publishes historical rates in a "Market Settlements Rates Factors" file on its Market Settlements page (per the monthly notices), behind the same Cloudflare check. **Ask Areeb to download it in a browser** into `data/inbox/` (§7).

**Round 27, a second source for RSG levels:** the IMM's annual *State of the Market* reports (Potomac Economics, potomaceconomics.com, not a MISO host) report allocated RSG per MWh. The 2024 report says day-ahead prices were about 2 % above real-time "after adjusting for the real-time RSG costs, which averaged $0.11 per MWh" (obs., 2024 report, p. 33; PDF SHA-256 `cfad6625…`). Its footnote defines the rate as "the Day-Ahead Deviation Charge (DDC) Rate, which excludes the location-specific Congestion Management Charge (CMC) Rate and Pass 2 RSG" (2023 appendix, fn. 9). An annual RSG history 2008–2024 can be assembled from these reports, but only as annual averages, not the hourly rates the settlement uses.

### 3.2 Proposed cost model for M3

Per asset owner (one bot = one asset owner), per hour h, with q⁺(n,h) DEC and q⁻(n,h) INC cleared MW at node n:

```
net(n,h)            = q⁺(n,h) − q⁻(n,h)                         MW, + is net demand
admin_usd(h)        = (schedule17 + schedule24)(month) × Σ_n |net(n,h)|
da_rsg_usd(h)       = da_rsg_rate(day)        × Σ_n max(net(n,h), 0)
rt_rsg_usd(h)       = ddc_rate(h, era)        × max(−Σ_n net(n,h), 0)
                    + cmc_allowance(era)      × Σ_n max(−net(n,h), 0)      # stand-in; constraints aren't modelled
fees_usd(h)         = admin_usd + da_rsg_usd + rt_rsg_usd                   # doubled in the G4 stress test
```

- Era switch for RSG: zero before 2008-11, the 2008-11 → 2011-03 regime, and post-2011-04 rates; values from the Rates Factors file once available, else D8's $1.8/MWh for the middle era and a documented assumption after.
- Netting is **per node** for Schedule 17/24 and DA RSG, but **across nodes** for DDC. That rewards a portfolio that balances INC and DEC. O3 (CVaR portfolio) should model it; it settles the `docs/design_spec.md` §20.6 [verify] "how MISO charges per bid vs per net position": **net, per asset owner**.
- This replaces the brief's `fees(q, cleared)` with a function of the whole day's position matrix. The M3 interface already takes a decision matrix (`docs/design_spec.md` §20.10), so it fits.

---

## 4. Credit, collateral and the Virtual MWh Limit

### 4.1 Collateral formula (Attachment L §IV.A, and the potential-exposure formula)

```
virtual potential exposure = Σ invoiced-unpaid virtual charges (VIE)
                           + Σ settled-not-invoiced virtual charges (VME)
                           + DMWhL × MPD × VMEW
```

(obs. D2, "3) Virtual Transaction Potential Exposure")

- **DMWhL**: the daily Virtual MWh Limit the participant chooses.
- **MPD**: "the greater of the highest differential between the Day-Ahead and Real-Time Locational Marginal Prices at the 50th percentile over the previous twelve (12) months, assessed during the month of April and implemented May 1 … or the Minimum MPD Value." **Minimum MPD Value = $12.00/MWh.** The first MPD (April 2006 → April 2007) was $13.33. (obs. D2)
- **VMEW** = 2 days. (obs. D2)
- MISO's 2023 credit task team: the calculated MPD was **$4.89 in 2021**, "the lowest level since shortly after MISO's Virtual Market began"; the historic 50th-percentile value was $12.05. The $12 floor was one of its proposals and is in v56.0.0. (obs. D4, pp. 9–11) So the MPD in recent years has been the **$12 floor**. The *published* MPD for May 2026 → April 2027 was not found [verify; MISO's credit page is behind Cloudflare]. When the floor was introduced, and what MPD applied in each year 2007–2023, is also [verify]; the backtest needs it only for the collateral check. **Decided (round 28):** until MISO's published values are supplied, the simulator uses the $12 floor for every year, labelled "estimate"; at Stage A it can't change any result.
- **Round 27, an attempt to compute the MPD history ourselves** (`tools/compute_mpd_history.py` → `docs/data/mpd_history.csv`):
  - **Reading tested:** for each hour of the day, the median |DA − RT| across all nodes over April → March; the MPD is the highest of the 24.
  - **Result: not MISO's method.** It gives $4.87 for 2021 (published $4.89), but $18.54 for 2006 (published $13.33) and $3.59 for 2016, which contradicts MISO calling 2021's $4.89 the lowest since the market's early days.
  - **The medians of our yearly values** ($8.15 since 2006, $5.50 over 2012–2021, $5.19 over 2017–2021) are also well below MISO's ($12.05, $10.23, $8.00).
  - **The floor's start** is taken as Attachment L v56.0.0 (effective 2024-06-03).
  - **Effect:** none at Stage A, where collateral is far below equity. At stages D and C the Virtual MWh Limit can bind.
- Full Stage A size: 936 MWh × $12 × 2 = **$22,464**, as in `docs/design_spec.md` §6.3. Confirmed.

### 4.2 The Virtual MWh Limit counts submitted, not cleared, MWh

- "The sum of the absolute value of Virtual Bid MWhs and the absolute value of Virtual Supply Offer MWhs **submitted** … for a given Operating Day may not exceed its Virtual MWh Limit. If both a Virtual Bid and a Virtual Supply Offer are submitted for a given Node, then the … greater of [the two] at that Node will be counted." (obs. D2 §IV.A.4)
- A new or raised limit takes effect within two calendar days after processing; a lowered limit reduces the credit requirement within at most nine days. (obs. D2 §IV.A.1–2; D1 says an allocation made on Monday is usable on Tuesday)

**For the simulator:** check the limit against **submitted** MWh (every bid block, cleared or not), with per-node max(DEC, INC). A bot with low limit prices that rarely clears still uses its whole limit. The brief's "virtual MW limit scales with collateral" (`docs/design_spec.md` §10.1, L1) should be read this way.

---

## 5. Who may trade: eligibility and minimum capitalization

### 5.1 Attachment L version

- The copy MISO hosts as "Attachment L – Credit Policy" is **v56.0.0, effective 2024-06-03** (obs. D2).
- MISO filed **v57.0.0** on 2025-07-14 (docket ER25-2845), requesting effect from 2025-07-15. It changes only an emergency-pricing LMP proxy for demand resources ($200 → $1,000). (obs. D3, pp. 5–6) A text comparison shows §III.B, §IV.A and the virtual exposure formula are **identical** in v56.0.0 and v57.0.0 apart from PDF glyph encoding (script in round 18 doc §3).
- Whether FERC accepted v57.0.0 was not confirmed, and no later version was found by search (round 27). For the rules used here it makes no difference unless a later version changed them.

### 5.2 "Appropriate person" status (§III.B)

Demonstrated in any one of these ways (obs. D2 §III.B):
- financial statements showing **net worth > $1 million or total assets > $5 million** (unaudited statements need an officer's signed memo);
- a **cash deposit > $5 million** with MISO;
- a corporate guaranty from a guarantor that is itself an appropriate person (and $1M net worth / $5M assets per guaranteed entity);
- an irrevocable letter of credit from an issuer that is an appropriate person;
- generally, meeting §4(c)(3)(F) of the Commodity Exchange Act.

The brief's "one of seven routes" came from MISO's *Minimum Participation Requirements* page, which wasn't read here; Attachment L itself lists the four mechanisms above plus the CEA wording.

### 5.3 Minimum capitalization (§III.C): a separate test

For a participant **not** trading FTRs (financial transmission rights), which is the evobots individual (obs. D2 §III.C):
- **tangible net worth ≥ $500,000 or total assets ≥ $5 million**, shown by **audited** financial statements for the latest fiscal year, filed every year by June 30 (or 120 days after fiscal year end); or
- **alternative capitalization: $200,000 of financial security** (cash or letter of credit), of which **50 % is set aside** and can't be used for trading. (With FTRs: $1M / $10M, or $500k.)

MISO's 2023 task team called the previous $50k alternative the lowest in the industry and proposed $200k (obs. D4, p. 6); v56.0.0 has $200k. Cash or a letter of credit are accepted as collateral; bonds are not. (obs. D13)

### 5.4 What this means for the career model

- With the $1.5M default, the individual meets §III.B (net worth > $1M) and §III.C (tangible net worth ≥ $500k). The optional absolute `ruin_floor_usd` of $1M "inspired by MISO's eligibility rule" (`docs/design_spec.md` §10.1) is consistent with §III.B's financial-statement route. The **§III.C floor is $500k** of tangible net worth (non-FTR); a ruin floor below that would leave a career trading while ineligible under the audited-statements route.
- **Fixed costs:** §III.C route 1 needs an **annual audit** of the trading company's financial statements. MISO itself charges no fixed annual participation fee that was found in these documents, nor by search in round 27 (which found only other ISOs' fees). The $50k/year fixed cost stays a labelled assumption. Admin charges are per MWh (§3).

---

## 6. Calendar: the `holiday` feature

The six NERC off-peak holidays, from the NAESB business practice recommendation (obs. D10): New Year's Day, Memorial Day, Independence Day, Labor Day, Thanksgiving, Christmas.

**Conflict (round 27: decided as below, pending Areeb's confirmation):** D10 (NAESB, last saved 2006) says "If any of these holidays fall on a Sunday, the following Monday will be considered an Off-Peak day." PJM's published *NERC 2027 Off-Peak Days* (obs. D11) lists **Independence Day on Sunday, July 4, 2027**, with no Monday substitute. Options for M2:
- **A (recommended):** flag the holiday on its calendar date, and also flag the Monday after a Sunday holiday (covers both readings; at most one extra day a year is flagged).
- **B:** follow the newest NERC document, once found, exactly.

Saturday holidays stay on Saturday in both sources.

---

## 7. Status of the M0 [verify] list

| Item (`docs/design_spec.md` §16) | Result | Status |
|---|---|---|
| Bid deadline | 10:30 EPT since 2016-11-05; 11:00 EST (noon EPT in summer) before | **resolved** for today and 2015; the exact 2016 change date and 2005–2007 rest on second-hand sources (§2.1). **Decided round 20 (D1):** the bot decides at 10:30 EPT on D−1 in every year, never later than the real deadline, so the remaining uncertainty no longer affects results |
| Admin fee | Schedule 17 + 24 ≈ $0.090/MWh (Oct 2026), on \|net\| per node-hour | **mechanics resolved**; rates [verify] (search-index source), history missing |
| RSG rates | mechanics and eras resolved (§3); one historical average ($1.8/MWh RSG1, 2008–2012 data) | **rates missing**: need the Rates Factors file |
| Holiday list | six NERC holidays | Sunday rule conflicting in the sources (§6); **decided round 20 (D2):** flag the Sunday and the following Monday |
| Published MPD | $12 floor binds in recent years; formula confirmed | current published value and 2007–2023 history [verify] |
| Settlement timing | S7 statement, weekly Tuesday invoices | **resolved** |
| Preliminary RT archive depth | not archived (only the last ~3 days) | **resolved** (obs. probe) |
| IMM volume limits | mentioned, not specified | **open**: BPM-009 / Module D not yet read |
| Attachment L v56.0.0 current? | v57.0.0 filed 2025-07; same text for virtual rules | **resolved for our purposes**; no later version found by search (round 27) |
| Individual's fixed yearly costs | no fixed MISO fee found; annual audit required (§III.C route 1) | **partly resolved**: costs of audit, accounting and legal are still assumptions (round 18 doc §5) |

### What Areeb can unblock
1. Download, in a browser, MISO's **Market Settlements Rates Factors** file (Markets and Operations → Settlements → Market Settlements → Related Documents) into `data/inbox/`. It should give the Schedule 17/24 and RSG rate history.
2. Optionally, the current **BPM-002** (energy markets) and **BPM-009** (market monitoring) from MISO's Business Practices Manuals page, also behind the browser check.

---

## 8. Documents read

All downloaded on 2026-10-23 into the git-ignored `data/raw/rules/` by `tools/fetch_rule_documents.py`.

| ID | Document | URL | SHA-256 |
|---|---|---|---|
| D1 | MISO, *Virtual Trading in MISO* (new market participant onboarding, PDF dated 2022-08-24, 13 pp.) | `https://cdn.misoenergy.org/Virtual%20Trading%20In%20MISO624133.pdf` | `5c59d443745bff8e514710ad4b3abdad2643feac1c8f81b81e885bfda94d90df` |
| D2 | MISO Tariff Attachment L, Credit Policy, v56.0.0, effective 2024-06-03 (185 pp.) | `https://cdn.misoenergy.org/Attachment%20L%20-%20Credit%20Policy586302.pdf` | `025606b28c4d662fc17b5c187fd3091f79337b4c11ee171ecb1b033bf5f7df1a` |
| D3 | MISO filing ER25-2845-000, 2025-07-14, with Attachment L v57.0.0 redline (476 pp.) | `https://cdn.misoenergy.org/2025-07-14%20Docket%20No.%20ER25-2845-000707828.pdf` | `26c7666213b0eabcb3703d04a53636604265d8b939e0dd247a0daf3cb6d88ff5` |
| D4 | MISO Credit Policy Enhancement Task Team, presentation, 2023-09-15 (15 pp.) | `https://cdn.misoenergy.org/20230915%20CPETT%20Item%2002-05%20Presentation630201.pdf` | `e98e9e63df55ede0b4daf8835c8954e2c378ea38c7e5825890771d8495212b52` |
| D5 | MISO, *Market Settlements 5 Minute Calculation Guide* MS-OP-029-r57r58 draft redline, effective 2026-01-29 / 2026-06-01 (412 pp.) | `https://cdn.misoenergy.org/MS-OP-029-r58_Market_Settlements_5_Minute_Calculation_Guide_DRAFT%20(UDE%20changes)745017.pdf` | `9c65862ab3e543d5bb3e2cf2dc99cc3a12e97768206854d595c70135d4bd4386` |
| D6 | Potomac Economics (MISO IMM), *2022 State of the Market Report, Analytical Appendix* (160 pp.) | `https://cdn.misoenergy.org/2022%20State%20of%20the%20Market%20Analytical%20Appendix629423.pdf` | `045c7e5e0631cbda32e2612b12b2e6c1afc2facfa8ec9ddc4f17e4e4b34e9a60` |
| D7 | Potomac Economics, *2024 State of the Market Report, Appendix* (167 pp.) | `https://www.potomaceconomics.com/wp-content/uploads/2025/07/2024-MISO-SOM_Appendix_Final.pdf` | `6392a233bb81d4f92fec9f68a1242a6617490014e3e7939d0f91bc99014bf8eb` |
| D8 | Birge, Hortaçsu, Mercadal & Pavlin, *Limits to Arbitrage in Electricity Markets: A Case Study of MISO*, MIT CEEPR WP 2017-003, January 2017 (66 pp.) | `https://ceepr.mit.edu/wp-content/uploads/2021/09/2017-003.pdf` | `3f6e196850bc0f46622a40be72cb478f3c1b8a2beb4a4fc7ad7cf76dc2827c7c` |
| D9 | FERC, *Order on Compliance Filing*, 153 FERC ¶ 61,317, dockets ER15-2256-000 and EL14-25-000, issued 2015-12-17 (32 pp.) | `https://ferc.gov/sites/default/files/2020-05/E-8_57.pdf` | `f0e34de44991dfb288c592b64dfcb24c7e960dd48f9106685c6c535f852c54d0` |
| D10 | NAESB recommendation R05007 (Word file, last saved 2006-03-24), off-peak holidays | `https://www.naesb.org/pdf2/r05007_rec.doc` | `a73d5d6527ec956eb7354756684e3f2bffddbfd66dd83b27f3d907c67fe7c34f` |
| D11 | PJM, *2027 Business Calendar* (NERC 2027 off-peak days) | `https://www.pjm.com/-/media/DotCom/markets-ops/settlements/2027-business-calendar.pdf` | `9f4e1f05fd74867da3212fff86a68ab98a897bb2f1c7a46d241119a3fb9fc822` |
| D12 | MISO help centre KA-01129, *Day-Ahead Market Timetable* (dynamic HTML) | `https://help.misoenergy.org/knowledgebase/article/KA-01129/en-us` | `85daba287c9d361608c8e6e9ede2b601e4ee44b68defd797870870c931ae2b25` (changes with page furniture) |
| D13 | MISO help centre KA-01086, *MISO Credit Collateral Requirements* (dynamic HTML) | `https://help.misoenergy.org/knowledgebase/article/KA-01086/en-us` | `993d466e94e44e780373f15dcceb3e0e55783134fe28a812c856aa23b77dda06` (changes with page furniture) |

Tried and not available: MISO's Market Reports Directory (`cdn.misoenergy.org/Market%20Reports%20Directory115139.xlsx`, HTTP 403 "AccessDenied" from the CDN, a stale link); the market-participation fact sheet (same); MISO's rate notices and BPM pages on `www.misoenergy.org` (Cloudflare challenge); the 2016 day-ahead timetable notice on `www.oasis.oati.com` (HTTP 503, three tries).

---

## 9. Measured vs assumed

**Measured (obs.):** every rule marked (obs. Dn) above, read in the downloaded document; the RT publication lag (4 days on 2026-10-23) and the preliminary-RT window (2026-10-20 → 22 only), from `tools/probe_rt_archive.py`; that the price server still publishes all three file eras and current days (2026-10-23); that Attachment L v56.0.0 and v57.0.0 have identical virtual-trading text.

**Assumed or unverified:** the Schedule 17/24 rates (search-index quotes of MISO notices); the 2016-11-05 deadline change date; that 11:00 EST already applied in 2005–2007; the sign convention behind "net virtual supply" in DDC (consistent with the IMM's wording, not checked in the BPM glossary); the current published MPD; IMM volume limits; the NERC Sunday-holiday rule; that MISO charges no fixed annual participation fee.
