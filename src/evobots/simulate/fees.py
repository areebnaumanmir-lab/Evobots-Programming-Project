"""Costs charged to cleared virtual trades, by month and era (`docs/market_rules.md` §3).

Per trader (one asset owner) and hour h, with net(n, h) = DEC MW − INC MW cleared at node n:

```
admin_usd(h)  = (Schedule 17 + Schedule 24 rate)(month) × Σ_n |net(n, h)|
da_rsg_usd(h) = DA RSG rate(day)                        × Σ_n max(net(n, h), 0)
rt_rsg_usd(h) = DDC rate(hour, era)                     × max(−Σ_n net(n, h), 0)
fees_usd(h)   = cost multiple × (admin + da_rsg + rt_rsg)
```

Netting is per node for the administration fee and DA RSG, and across nodes for the
real-time deviation charge (DDC), as MISO's settlement formulas state (`market_rules.md`
§3, obs. D5). The location-specific Constraint Management Charge is not modelled (no
constraint data), which the report states.

**Rates are labelled.** Until MISO's *Market Settlements Rates Factors* file arrives (R1,
round 28), every rate below is an **estimate**:

- Schedule 17 + 24: $0.0902/MWh every month (October 2026 notices as quoted by a search
  index [verify]);
- DA RSG on net virtual demand: $0.05/MWh from 2008-11 (placeholder, no source: a small
  charge so DEC isn't free);
- DDC on net virtual supply: $0 to 2008-10 ("virtual transactions were not subject to RSG
  charges", Birge et al. 2017, D8); $1.80/MWh 2008-11 → 2011-03 (D8's mean first-pass RSG
  rate, 2008–2012 data); $0.11/MWh from 2011-04 (IMM 2024 State of the Market, DDC rate).

The G4 stress test doubles every rate (cost multiple 2).

Example:
    >>> import datetime
    >>> table = CostTable.estimates()
    >>> rates = table.rates_for_day(datetime.date(2010, 6, 1))
    >>> rates.ddc_usd_per_mwh, rates.label
    (1.8, 'estimate')
    >>> # 2 MW DEC at one hub, 5 MW INC at another: admin on 7 MW, DA RSG on 2, DDC on 3
    >>> round(hourly_fees_usd([2.0, -5.0], rates), 4)
    6.1314
"""

import dataclasses
import datetime

import numpy as np

# Era boundaries for RSG on virtual supply (market_rules.md §3.1).
RSG_ON_VIRTUALS_FIRST_DAY = datetime.date(2008, 11, 1)
RSG_REFORM_FIRST_DAY = datetime.date(2011, 4, 1)
# Schedule 17 ($0.0746) + Schedule 24 ($0.0156), October 2026, USD per MWh [verify].
ADMIN_FEE_ESTIMATE_USD_PER_MWH = 0.0902
# DA RSG on net virtual demand: placeholder (no published history in the project).
DA_RSG_PLACEHOLDER_USD_PER_MWH = 0.05
# DDC on net virtual supply by era: none, D8's 2008–2012 mean, IMM 2024 average.
DDC_BY_ERA_USD_PER_MWH = (0.0, 1.80, 0.11)


@dataclasses.dataclass(frozen=True)
class DayRates:
    """The rates that apply on one operating day.

    Attributes:
        admin_usd_per_mwh: Schedule 17 + 24, on |net| per node-hour.
        da_rsg_usd_per_mwh: DA RSG, on net virtual demand per node-hour.
        ddc_usd_per_mwh: RT RSG (DDC), on net virtual supply summed over nodes, per hour;
            a float, or 24 hourly values when known hour by hour.
        label: "measured" (from MISO's rate file) or "estimate".
    """

    admin_usd_per_mwh: float
    da_rsg_usd_per_mwh: float
    ddc_usd_per_mwh: float
    label: str


@dataclasses.dataclass(frozen=True)
class CostTable:
    """Rates by day. `estimates()` gives the labelled placeholder table above."""

    source: str
    rates_by_month: dict = dataclasses.field(default_factory=dict)

    @classmethod
    def estimates(cls):
        """The estimate table (`docs/market_rules.md` §3, D3)."""
        return cls(source="estimates (Rates Factors file not yet supplied)")

    def rates_for_day(self, day):
        """DayRates for an operating day (a measured month overrides the estimate)."""
        measured = self.rates_by_month.get((day.year, day.month))
        if measured is not None:
            return measured
        if day < RSG_ON_VIRTUALS_FIRST_DAY:
            era = 0
        elif day < RSG_REFORM_FIRST_DAY:
            era = 1
        else:
            era = 2
        return DayRates(
            admin_usd_per_mwh=ADMIN_FEE_ESTIMATE_USD_PER_MWH,
            da_rsg_usd_per_mwh=DA_RSG_PLACEHOLDER_USD_PER_MWH if era else 0.0,
            ddc_usd_per_mwh=DDC_BY_ERA_USD_PER_MWH[era],
            label="estimate",
        )

    def daily_arrays(self, days, cost_multiple=1.0):
        """(admin, da_rsg, ddc) rate arrays for some days, shapes (days,), (days,), (days, 24)."""
        rates = [self.rates_for_day(day) for day in days]
        admin = np.array([rate.admin_usd_per_mwh for rate in rates]) * cost_multiple
        da_rsg = np.array([rate.da_rsg_usd_per_mwh for rate in rates]) * cost_multiple
        ddc = (
            np.array([np.broadcast_to(rate.ddc_usd_per_mwh, (24,)) for rate in rates])
            * cost_multiple
        )
        return admin, da_rsg, ddc

    def labels(self, days):
        """The set of labels used over some days ({"estimate"} until the file arrives)."""
        return {self.rates_for_day(day).label for day in days}


def hourly_fees_usd(net_mw_by_node, rates, hour_index=0, cost_multiple=1.0):
    """Fees for one hour of one trader, USD (readable reference of the formula above).

    Args:
        net_mw_by_node: DEC MW − INC MW cleared at each node in the hour.
        rates: DayRates.
        hour_index: 0–23, used when the DDC rate is hourly.
        cost_multiple: 2 for the doubled-cost stress test.
    """
    net = np.asarray(net_mw_by_node, dtype=float)
    ddc = np.broadcast_to(rates.ddc_usd_per_mwh, (24,))[hour_index]
    admin = rates.admin_usd_per_mwh * np.abs(net).sum()
    da_rsg = rates.da_rsg_usd_per_mwh * np.maximum(net, 0.0).sum()
    rt_rsg = ddc * max(-net.sum(), 0.0)
    return float(cost_multiple * (admin + da_rsg + rt_rsg))
