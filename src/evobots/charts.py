"""Server-side SVG charts in the project's visual style (`docs/design_spec.md` §14.5).

Ink and greys only; one signal colour (via the theme's `--colour-signal`) for losses and
deaths; no fills behind charts; square corners. Every chart is plain SVG text computed here,
so the browser never computes a result (§14.5: "the UI never computes results").

Example:
    >>> svg = line_chart([("2024-01-01", 1.0), ("2024-01-02", 2.0)], "equity")
    >>> svg.startswith("<svg") and "polyline" in svg
    True
"""

import html

import numpy as np

WIDTH = 720
# Points per line after server-side thinning (about one per pixel of the 720-wide chart).
MAX_POINTS = 600
HEIGHT = 200


def escape(value):
    """HTML-escaped text."""
    return html.escape(str(value))


def number_label(value, unit):
    """A short axis label."""
    if unit == "$":
        return f"${value:,.0f}"
    if unit == "%":
        return f"{value:.0%}"
    return f"{value:,.4g}"


def thinned(points, max_points=MAX_POINTS):
    """At most max_points evenly spaced points, always keeping the first and the last.

    Thinning happens here, on the server, so a 20-year daily chart sends ≈ 600 points.

    Example:
        >>> [x for x, _ in thinned([(day, 0.0) for day in range(10)], 4)]
        [0, 3, 6, 9]
    """
    if len(points) <= max_points:
        return list(points)
    positions = np.unique(np.linspace(0, len(points) - 1, max_points).round().astype(int))
    return [points[position] for position in positions]


def line_chart(points, label, unit="$", series=None, width=WIDTH, height=HEIGHT):
    """Lines of (x label, value) points; `series` adds more as {name: points} (greys).

    Each line is thinned to MAX_POINTS on the server first.
    """
    points = thinned(points)
    series = {name: thinned(line) for name, line in (series or {}).items()}
    all_series = {label: points, **series}
    values = [value for line in all_series.values() for _, value in line if value == value]
    if len(points) < 2 or not values:
        return '<p class="description">Not enough data to draw.</p>'
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    shades = ["var(--colour-ink)", "#888888", "#bbbbbb", "#555555"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{escape(label)}">'
    ]
    for index, (name, line) in enumerate(all_series.items()):
        step = (width - 2) / max(len(line) - 1, 1)
        coordinates = " ".join(
            f"{position * step + 1:.1f},{height - 20 - (value - low) / span * (height - 40):.1f}"
            for position, (_, value) in enumerate(line)
            if value == value
        )
        parts.append(
            f'<polyline points="{coordinates}" fill="none" stroke="{shades[index % len(shades)]}" '
            f'stroke-width="1"><title>{escape(name)}</title></polyline>'
        )
    if low < 0 < high:
        zero = height - 20 - (0 - low) / span * (height - 40)
        parts.append(
            f'<line x1="0" x2="{width}" y1="{zero:.1f}" y2="{zero:.1f}" '
            'stroke="var(--colour-hairline)"/>'
        )
    parts.append(f'<text x="2" y="12" class="axis">{escape(number_label(high, unit))}</text>')
    parts.append(
        f'<text x="2" y="{height - 4}" class="axis">{escape(number_label(low, unit))}</text>'
    )
    parts.append(
        f'<text x="{width - 2}" y="{height - 4}" text-anchor="end" class="axis">'
        f"{escape(points[0][0])} → {escape(points[-1][0])}</text></svg>"
    )
    return "".join(parts)


def bar_chart(items, label, unit="", width=WIDTH):
    """Horizontal bars for (name, value) items; negative values in the signal colour."""
    if not items:
        return '<p class="description">Nothing to draw.</p>'
    row_height = 20
    height = row_height * len(items) + 10
    largest = max(abs(value) for _, value in items) or 1.0
    label_width = 220
    middle = (
        label_width + (width - label_width) / 2
        if any(value < 0 for _, value in items)
        else label_width
    )
    scale = (width - middle - 70) / largest
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{escape(label)}">'
    ]
    for index, (name, value) in enumerate(items):
        top = 5 + index * row_height
        length = abs(value) * scale
        left = middle if value >= 0 else middle - length
        colour = "var(--colour-signal)" if value < 0 else "var(--colour-ink)"
        parts.append(
            f'<text x="{label_width - 6}" y="{top + 13}" text-anchor="end" '
            f'class="axis">{escape(name)}</text>'
        )
        parts.append(
            f'<rect x="{left:.1f}" y="{top + 4}" width="{max(length, 0.5):.1f}" height="10" '
            f'fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{(middle + length + 4) if value >= 0 else middle + 4:.1f}" y="{top + 13}" '
            'class="axis">'
            f"{escape(number_label(value, unit))}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def grid_map(cells, columns, rows, cell_size=30, link=None):
    """The MAP-Elites map: cells {(column, row): (value, title)} shaded by value (ink = best).

    A white cell is empty. Columns run from all-INC (left) to all-DEC (right); rows from
    rarely bidding (bottom) to bidding nearly every location-hour (top).
    """
    values = [value for value, _ in cells.values()] or [0.0]
    low, high = min(values), max(values)
    width, height = columns * cell_size + 2, rows * cell_size + 2
    parts = [
        f'<svg viewBox="0 0 {width + 120} {height + 30}" width="{width + 120}" role="img" '
        'aria-label="map">'
    ]
    for column in range(columns):
        for row in range(rows):
            left, top = column * cell_size + 1, (rows - 1 - row) * cell_size + 1
            entry = cells.get((column, row))
            if entry is None:
                fill, title = "#ffffff", "empty: no surviving trader of this kind yet"
            else:
                share = (entry[0] - low) / ((high - low) or 1.0)
                grey = int(225 - share * 205)
                fill, title = f"rgb({grey},{grey},{grey})", entry[1]
            rectangle = (
                f'<rect x="{left}" y="{top}" width="{cell_size}" height="{cell_size}" '
                f'fill="{fill}" '
                f'stroke="var(--colour-hairline)"><title>{escape(title)}</title></rect>'
            )
            if entry is not None and link is not None:
                rectangle = f'<a href="{escape(link(column, row))}">{rectangle}</a>'
            parts.append(rectangle)
    parts.append(f'<text x="0" y="{height + 14}" class="axis">only INC</text>')
    parts.append(
        f'<text x="{width}" y="{height + 14}" text-anchor="end" class="axis">only DEC</text>'
    )
    parts.append(f'<text x="{width + 6}" y="12" class="axis">bids on 100 %</text>')
    parts.append(f'<text x="{width + 6}" y="{height}" class="axis">bids on 0.1 %</text>')
    parts.append("</svg>")
    return "".join(parts)
