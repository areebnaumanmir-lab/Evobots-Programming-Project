"""Data settings: which sources may leave this machine in a shareable bundle (round 25).

MISO's terms forbid redistribution, so MISO-derived files are built locally and left out of
any shareable bundle unless the user switches `is_miso_redistribution_allowed` on, which
they should do only with MISO's written permission (`docs/data_sources.md` §3). The other
sources are public domain or CC BY and may be shared with their acknowledgments.

Example:
    >>> shareable_sources(DataSettings())
    ('eia', 'epu', 'fred', 'gpr', 'nws', 'worldbank')
    >>> "miso" in shareable_sources(DataSettings(is_miso_redistribution_allowed=True))
    True
"""

from dataclasses import dataclass

# Sources whose terms allow redistribution with acknowledgment (docs/data_sources.md §2).
FREELY_SHAREABLE_SOURCES = ("eia", "epu", "fred", "gpr", "nws", "worldbank")


@dataclass(frozen=True)
class DataSettings:
    """The `[data]` table.

    Attributes:
        is_miso_redistribution_allowed: True only with MISO's written permission; when
            False (the default), shareable bundles leave out every MISO-derived file.
    """

    is_miso_redistribution_allowed: bool = False

    def __post_init__(self):
        """Reject non-boolean values (a TOML string "false" would otherwise read as true)."""
        if not isinstance(self.is_miso_redistribution_allowed, bool):
            raise ValueError("is_miso_redistribution_allowed must be true or false")


def shareable_sources(settings):
    """The sources whose files may go into a shareable bundle under these settings."""
    if settings.is_miso_redistribution_allowed:
        return tuple(sorted((*FREELY_SHAREABLE_SOURCES, "miso")))
    return FREELY_SHAREABLE_SOURCES
