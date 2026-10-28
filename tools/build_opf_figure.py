"""Draw docs/explanations/figures/three_bus_opf.svg from the solved three-bus DC OPF.

Usage:
    python tools/build_opf_figure.py

Every number on the figure comes from evobots.orfe.dc_opf.solve_dc_opf(THREE_BUS_EXAMPLE);
nothing is typed in by hand. Colours follow docs/design/theme.css: ink, secondary grey,
and the signal red only for the binding line.
"""

from pathlib import Path

from evobots.orfe.dc_opf import THREE_BUS_EXAMPLE, solve_dc_opf

OUTPUT_PATH = Path("docs/explanations/figures/three_bus_opf.svg")
INK = "#111111"
SECONDARY = "#5f5f5f"
SIGNAL = "#a3271f"
BUS_POSITIONS = {0: (300, 230), 1: (620, 230), 2: (460, 60)}
LABEL_OFFSETS = {0: (-100, 40), 1: (-60, 40), 2: (25, -15)}


def figure_svg():
    """The figure as an SVG string."""
    result = solve_dc_opf(THREE_BUS_EXAMPLE)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 320" '
        'font-family="-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif" '
        'font-size="13">',
        '<rect width="860" height="320" fill="#ffffff"/>',
    ]
    for index, line in enumerate(THREE_BUS_EXAMPLE.lines):
        (from_left, from_top) = BUS_POSITIONS[line.from_bus]
        (to_left, to_top) = BUS_POSITIONS[line.to_bus]
        is_binding = result["line_shadow_price_usd_per_mwh"][index] > 0
        colour = SIGNAL if is_binding else INK
        width = 2.5 if is_binding else 1.2
        parts.append(
            f'<line x1="{from_left}" y1="{from_top}" x2="{to_left}" y2="{to_top}" '
            f'stroke="{colour}" '
            f'stroke-width="{width}"/>'
        )
        flow = result["flow_mw"][index]
        names = THREE_BUS_EXAMPLE.bus_names
        sender, receiver = (
            (line.from_bus, line.to_bus) if flow >= 0 else (line.to_bus, line.from_bus)
        )
        label = f"{names[sender]}→{names[receiver]} {abs(flow):.0f} MW"
        if line.limit_mw is not None:
            label += f" (limit {line.limit_mw:.0f}"
            label += f"; shadow price ${result['line_shadow_price_usd_per_mwh'][index]:.0f})"
        middle_left, middle_top = (from_left + to_left) / 2, (from_top + to_top) / 2
        is_horizontal = from_top == to_top
        anchor = "middle" if is_horizontal else ("end" if middle_left < 460 else "start")
        offset_left = 0 if anchor == "middle" else (-12 if anchor == "end" else 12)
        offset_top = 22 if is_horizontal else 0
        parts.append(
            f'<text x="{middle_left + offset_left:.0f}" y="{middle_top + offset_top:.0f}" '
            f'text-anchor="{anchor}" fill="{colour}">{label}</text>'
        )
    generation_by_bus = {}
    for generator, output in zip(THREE_BUS_EXAMPLE.generators, result["dispatch_mw"]):
        generation_by_bus[generator.bus] = (generator, output)
    for bus, (left, top) in BUS_POSITIONS.items():
        parts.append(f'<circle cx="{left}" cy="{top}" r="7" fill="{INK}"/>')
        label_left, label_top = LABEL_OFFSETS[bus]
        lines = [
            f"Bus {THREE_BUS_EXAMPLE.bus_names[bus]}: LMP ${result['lmp_usd_per_mwh'][bus]:.0f}/MWh"
        ]
        if bus in generation_by_bus:
            generator, output = generation_by_bus[bus]
            lines.append(f"generator ${generator.cost_usd_per_mwh:.0f}/MWh, runs {output:.0f} MW")
        load_mw = THREE_BUS_EXAMPLE.load_mw_by_bus[bus]
        if load_mw:
            lines.append(f"load {load_mw:.0f} MW")
        for line_number, text in enumerate(lines):
            weight = "600" if line_number == 0 else "400"
            colour = INK if line_number == 0 else SECONDARY
            parts.append(
                f'<text x="{left + label_left}" y="{top + label_top + 17 * line_number}" '
                f'font-weight="{weight}" fill="{colour}">{text}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    OUTPUT_PATH.write_text(figure_svg(), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
