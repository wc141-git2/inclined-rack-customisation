#!/usr/bin/env python3
"""Quote email → 3D model, in one step (completely standalone).

Reads the customer quote email and directly writes the parametric OpenSCAD
model:

    python make-it_3d.py < q.txt
    →  Wrote SCAD_DYNAMIC/rack_3d.scad

This script is **fully standalone**: the quote parser and the 3D geometry /
.scad template are all inlined here. It has no runtime dependency on any other
file in this repository, so it can be copied and run anywhere. The only output
is the path of the written file: ``Wrote SCAD_DYNAMIC/rack_3d.scad``.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import re
import sys
from dataclasses import dataclass

OUTPUT_DIR_DEFAULT = "SCAD_DYNAMIC"

# ===========================================================================
# QUOTE PARSING — the customer configurator's email format
# ===========================================================================

PARAMETER_MAP = [
    (
        "Rack inner width",
        "innerWidth",
        "--inner-width",
        "Clear width between the side panels.",
    ),
    ("Rack depth", "depth", "--depth", "Front-to-back depth of the rack."),
    (
        "Rack height",
        "innerHeight",
        "(auto-calculated)",
        "Clear inside height; used for verification, not passed to the generator.",
    ),
    (
        "Shelf slope",
        "drop",
        "--drop",
        "Vertical difference between the front and back of each shelf.",
    ),
    (
        "Shelf levels (total)",
        "shelfLevels",
        "--fixed-shelves / --flexible-shelves",
        "Total shelf count; split into fixed + flexible.",
    ),
    (
        "Flexible shelf levels",
        "flexibleShelves",
        "--flexible-shelves",
        "Number of shelves using the alternate top position.",
    ),
    (
        "Alternate shelf position height",
        "flexibleGrooveOffset",
        "--flexible-groove-offset",
        "Additional height of the alternate groove position.",
    ),
    (
        "Fixed-shelf height",
        "interShelfClearance",
        "--inter-shelf-clearance",
        "Clear vertical opening between standard shelf levels.",
    ),
    (
        "Side panel thickness",
        "sidePanelThickness",
        "--side-panel-thickness",
        "Thickness of the left and right side panels.",
    ),
    (
        "Back panel thickness",
        "backPanelThickness",
        "--back-panel-thickness",
        "Thickness of the rear panel.",
    ),
    (
        "Top open height at the front",
        "topClearance",
        "--top-clearance",
        "Clear vertical space above the top shelf.",
    ),
    (
        "Shelf thickness",
        "shelfThickness",
        "--shelf-thickness",
        "Thickness of each shelf panel.",
    ),
    (
        "Bottom clearance",
        "bottomClearance",
        "--bottom-clearance",
        "Clear vertical space below the lowest shelf (Advanced section).",
    ),
    (
        "Side margin",
        "sideMargin",
        "--side-margin",
        "Extra blank material beyond the rack depth per side (Advanced section).",
    ),
]

TECHNICAL_DEFAULTS = {
    "back_panel_thickness": 8.0,
    "flexible_groove_offset": 20.0,
    "groove_cut_width": 5.0,
    "bottom_clearance": 10.0,
    "top_clearance": 10.0,
    "default_flexible_shelves": 1,
}


@dataclass
class ParsedQuote:
    inner_width: float
    depth: float
    rack_height: float | None
    drop: float
    shelf_levels: int
    inter_shelf_clearance: float
    top_clearance: float
    side_panel_thickness: float
    shelf_thickness: float
    back_panel_thickness: float = 8.0
    bottom_clearance: float = 10.0
    side_margin: float = 10.0
    flexible_shelves: int | None = None
    flexible_groove_offset: float | None = None


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def parse_quote(text: str) -> ParsedQuote:
    patterns = {
        "inner_width": r"Rack inner width:\s*([\d.,]+)\s*mm",
        "depth": r"Rack depth:\s*([\d.,]+)\s*mm",
        "rack_height": r"Rack height:\s*([\d.,]+)\s*mm",
        "drop": r"Shelf slope:\s*([\d.,]+)\s*mm",
        "shelf_levels": r"Shelf levels:\s*(\d+)\b",
        "inter_shelf_clearance": r"Fixed-shelf height:\s*([\d.,]+)\s*mm",
        "top_clearance": r"Top clearance:\s*([\d.,]+)\s*mm",
        "panel_thickness": r"Panel / shelf thickness:\s*([\d.,]+)\s*/\s*([\d.,]+)\s*mm",
        "side_panel_thickness": r"Side panel thickness:\s*([\d.,]+)\s*mm",
        "back_panel_thickness": r"Back panel thickness:\s*([\d.,]+)\s*mm",
        "shelf_thickness": r"Shelf thickness:\s*([\d.,]+)\s*mm",
        "bottom_clearance": r"Bottom clearance:\s*([\d.,]+)\s*mm",
        "side_margin": r"Side margin:\s*([\d.,]+)\s*mm",
        "flexible_shelves": r"Flexible shelf levels:\s*(\d+)\b",
        "flexible_groove_offset": r"Alternate shelf position height:\s*([\d.,]+)\s*mm",
    }

    found: dict[str, str | tuple[str, str]] = {}
    missing: list[str] = []

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found[key] = match.groups() if key == "panel_thickness" else match.group(1)
        elif key not in (
            "rack_height",
            "panel_thickness",
            "side_panel_thickness",
            "back_panel_thickness",
            "shelf_thickness",
            "bottom_clearance",
            "side_margin",
            "flexible_shelves",
            "flexible_groove_offset",
        ):
            missing.append(key.replace("_", " "))

    if missing:
        raise ValueError("Could not find: " + ", ".join(missing))
    if "panel_thickness" not in found and "side_panel_thickness" not in found:
        raise ValueError("Could not find: panel thickness")
    if "panel_thickness" not in found and "shelf_thickness" not in found:
        raise ValueError("Could not find: shelf thickness")

    panel = found.get("panel_thickness")  # type: ignore[misc]
    combo_side, combo_shelf = panel if panel is not None else (None, None)
    side_panel = (
        _number(str(found["side_panel_thickness"]))
        if "side_panel_thickness" in found
        else _number(str(combo_side))
    )
    shelf = (
        _number(str(found["shelf_thickness"]))
        if "shelf_thickness" in found
        else _number(str(combo_shelf))
    )
    back_panel = (
        _number(str(found["back_panel_thickness"]))
        if "back_panel_thickness" in found
        else TECHNICAL_DEFAULTS["back_panel_thickness"]
    )

    return ParsedQuote(
        inner_width=_number(str(found["inner_width"])),
        depth=_number(str(found["depth"])),
        rack_height=(
            _number(str(found["rack_height"])) if "rack_height" in found else None
        ),
        drop=_number(str(found["drop"])),
        shelf_levels=int(str(found["shelf_levels"])),
        inter_shelf_clearance=_number(str(found["inter_shelf_clearance"])),
        top_clearance=_number(str(found["top_clearance"])),
        side_panel_thickness=side_panel,
        back_panel_thickness=back_panel,
        shelf_thickness=shelf,
        bottom_clearance=(
            _number(str(found["bottom_clearance"]))
            if "bottom_clearance" in found
            else TECHNICAL_DEFAULTS["bottom_clearance"]
        ),
        side_margin=(
            _number(str(found["side_margin"])) if "side_margin" in found else 10.0
        ),
        flexible_shelves=(
            int(str(found["flexible_shelves"])) if "flexible_shelves" in found else None
        ),
        flexible_groove_offset=(
            _number(str(found["flexible_groove_offset"]))
            if "flexible_groove_offset" in found
            else None
        ),
    )


def shelf_split(shelf_levels: int) -> tuple[int, int]:
    """Match the customer configurator: one flexible top shelf when possible."""
    flexible = min(TECHNICAL_DEFAULTS["default_flexible_shelves"], shelf_levels)
    fixed = shelf_levels - flexible
    if fixed < 0:
        raise ValueError("Shelf levels must be at least 1")
    return fixed, flexible


def resolve_shelf_counts(quote: ParsedQuote) -> tuple[int, int]:
    """(fixed, flexible) shelf split, honoring an explicit quote or the
    configurator's default rule (one flexible top shelf when possible)."""
    if quote.flexible_shelves is not None:
        if not 0 <= quote.flexible_shelves <= quote.shelf_levels:
            raise ValueError(
                f"Flexible shelf levels ({quote.flexible_shelves}) cannot exceed total shelf levels ({quote.shelf_levels})"
            )
        return quote.shelf_levels - quote.flexible_shelves, quote.flexible_shelves
    # Backward compatibility: older quotes without flexible info default to
    # the customer configurator rule (one flexible top shelf when possible).
    return shelf_split(quote.shelf_levels)


def resolve_flexible_offset(quote: ParsedQuote) -> float:
    """Flexible groove offset, falling back to the technical default."""
    if quote.flexible_groove_offset is None:
        return TECHNICAL_DEFAULTS["flexible_groove_offset"]
    return quote.flexible_groove_offset


def print_parameter_map() -> None:
    print("Customer language → script parameter map\n")
    print(f"{'Customer wording':<32} {'Script parameter':<22} {'CLI flag':<28} Meaning")
    print("-" * 110)
    for customer, script, flag, meaning in PARAMETER_MAP:
        print(f"{customer:<32} {script:<22} {flag:<28} {meaning}")


def print_technical_defaults() -> None:
    print("Technical defaults used when the email does not include a field\n")
    for key, value in TECHNICAL_DEFAULTS.items():
        print(f"  {key}: {value}")
    print(
        "\nShelf split rule: fixed = shelf_levels - 1, flexible = 1 (when shelf_levels >= 1)"
    )


def read_quote_input() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read()

    print("Paste the quote email below.")
    print("Finish with a blank line (or press Ctrl-D / Ctrl-Z):\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# 3D GEOMETRY — derived from the quote's dimensions
# ===========================================================================


@dataclass
class RackParameters:
    inner_width: float = 100.0
    inner_height: float | None = None
    fixed_shelves: int = 3
    flexible_shelves: int = 1
    depth: float = 270.0
    drop: float = 25.0
    side_panel_thickness: float = 8.0
    back_panel_thickness: float = 8.0
    bottom_clearance: float = 10.0
    top_clearance: float = 10.0
    inter_shelf_clearance: float = 100.0
    flexible_groove_offset: float = 20.0
    shelf_thickness: float = 5.0
    groove_cut_width: float = 5.0
    hole_y_positions: tuple[float, float] = (0.2, 1.0)
    visible_holes: tuple[int, ...] = (1, 2, 5, 12, 14)
    side_margin: float = 10.0

    def validate(self) -> None:
        positive = {
            "inner_width": self.inner_width,
            "depth": self.depth,
            "drop": self.drop,
            "side_panel_thickness": self.side_panel_thickness,
            "back_panel_thickness": self.back_panel_thickness,
            "bottom_clearance": self.bottom_clearance,
            "top_clearance": self.top_clearance,
            "inter_shelf_clearance": self.inter_shelf_clearance,
            "flexible_groove_offset": self.flexible_groove_offset,
            "shelf_thickness": self.shelf_thickness,
            "groove_cut_width": self.groove_cut_width,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
        for name in ("bottom_clearance", "top_clearance"):
            value = getattr(self, name)
            if value < 10.0:
                raise ValueError(f"{name} must be at least 10, got {value}")
        if self.side_margin < 8.0:
            raise ValueError(f"side_margin must be at least 8, got {self.side_margin}")
        if self.fixed_shelves < 0 or self.flexible_shelves < 0:
            raise ValueError("Shelf counts cannot be negative")
        if self.fixed_shelves + self.flexible_shelves == 0:
            raise ValueError("At least one shelf is required")
        if self.inner_height is not None and self.inner_height <= 0:
            raise ValueError("inner_height must be greater than zero")
        if len(self.hole_y_positions) != 2 or any(
            not 0.0 <= p <= 2.0 for p in self.hole_y_positions
        ):
            raise ValueError("hole_y_positions must contain two values from 0.0 to 2.0")
        if any(int(h) <= 0 for h in self.visible_holes):
            raise ValueError("visible_holes must contain positive hole numbers")


GROOVE_DEPTH = 3.3  # partial-depth groove cut into the side panel
SHELF_FIT_CLEARANCE = 0.5  # shelf width = back panel width - 0.5
SHELF_CLEARANCE_Y = 1.0  # shelf length slack along the depth axis
HOLE_DIAMETER = 4.3  # all round holes
CORNER_HOLE_GROOVE_CLEARANCE = 2.0
SIDE_HOLE_GROOVE_CLEARANCE = 2.0
BACK_GROOVE_EDGE_INSET = 4.0
BACK_PANEL_GROOVE_CLEARANCE = 0.2
RACK_FRONT_INSET = 1.0  # front panel plane sits this far inside the front cut edge
GROOVE_OVEREXTEND = 2.0  # sloped groove overcut past the blank's front edge
CORNER_HOLE_12_BOTTOM_DISTANCE = 100.0
CORNER_HOLE_TOP_BOTTOM_DISTANCE = 15.0


class RackGeometry:
    """All derived dimensions and shelf/hole positions for the 3D model."""

    def __init__(self, p: RackParameters):
        p.validate()
        self.p = p
        count = p.fixed_shelves + p.flexible_shelves

        self.rack_width = p.inner_width + 2.0 * p.side_panel_thickness
        self.blank_depth = p.depth + 2.0 * p.side_margin
        self.side_thickness = p.side_panel_thickness
        self.back_thickness = p.back_panel_thickness
        self.shelf_thickness = p.shelf_thickness
        self.groove_cut_width = p.groove_cut_width

        self.front_panel_y = p.side_margin + RACK_FRONT_INSET
        self.back_panel_y = p.side_margin + p.depth - 9.0
        self.back_panel_width = self.rack_width - 2.0 * (
            self.side_thickness - GROOVE_DEPTH
        )
        self.shelf_width = self.back_panel_width - SHELF_FIT_CLEARANCE
        self.shelf_fy = self.front_panel_y + SHELF_CLEARANCE_Y / 2.0
        self.shelf_by = self.back_panel_y - SHELF_CLEARANCE_Y / 2.0
        self.groove_dx = self.side_thickness - GROOVE_DEPTH

        usable = self.back_panel_y - self.front_panel_y  # = depth - 10
        angle = math.atan(p.drop / usable)
        self.angle = angle
        groove_height = p.groove_cut_width / (1.0 + angle * angle) ** 0.5

        # primary shelf positions (physical shelves)
        specs: list[tuple[str, float, float]] = []
        back_bottom = p.bottom_clearance
        for index in range(count):
            if index < p.fixed_shelves:
                name = f"FIXED_SHELF_{index + 1:02d}"
            else:
                name = f"FLEXIBLE_SHELF_{index - p.fixed_shelves + 1:02d}"
            back_center = back_bottom + groove_height / 2.0
            front_center = back_center + p.drop
            specs.append((name, front_center, back_center))
            back_bottom += groove_height + p.inter_shelf_clearance

        # flexible alternative grooves are extra slots for the same shelf
        alternative_specs = [
            (
                f"{name}_ALT",
                front_center + p.flexible_groove_offset,
                back_center + p.flexible_groove_offset,
            )
            for name, front_center, back_center in specs[p.fixed_shelves :]
        ]
        self.shelf_specs = [(f, b) for _, f, b in specs]
        self.cut_specs = [(f, b) for _, f, b in specs] + [
            (f, b) for _, f, b in alternative_specs
        ]
        # Alternate-position pairs, aligned with shelf_specs: flexible shelves
        # get their higher position (view_alternative); fixed shelves keep the
        # primary pair (unused, guarded by idx >= num_fixed in the .scad).
        self.alt_specs = [
            (
                (f + p.flexible_groove_offset, b + p.flexible_groove_offset)
                if index >= p.fixed_shelves
                else (f, b)
            )
            for index, (_, f, b) in enumerate(specs)
        ]

        highest_groove_extension = (
            p.flexible_groove_offset if p.flexible_shelves else 0.0
        )
        calculated_height = (
            p.bottom_clearance
            + count * groove_height
            + max(0, count - 1) * p.inter_shelf_clearance
            + p.drop
            + highest_groove_extension
            + p.top_clearance
        )
        if p.inner_height is None:
            self.rack_height = calculated_height
        else:
            top_groove_top_front = (
                specs[-1][1] + groove_height / 2.0 + highest_groove_extension
            )
            top_clearance = p.inner_height - top_groove_top_front
            if top_clearance < 0:
                raise ValueError(
                    f"inner_height={p.inner_height:.2f} is too short; "
                    f"the shelf stack requires at least {top_groove_top_front:.2f} mm before top clearance"
                )
            self.rack_height = p.inner_height

        self.back_panel_height = (
            self.rack_height
            - 2.0 * BACK_GROOVE_EDGE_INSET
            - 2.0 * BACK_PANEL_GROOVE_CLEARANCE
        )
        self.back_panel_z = BACK_GROOVE_EDGE_INSET + BACK_PANEL_GROOVE_CLEARANCE

        # support-rod holes (perpendicular drop below the sloped groove)
        support_drop = (
            p.groove_cut_width / 2.0 + HOLE_DIAMETER / 2.0 + SIDE_HOLE_GROOVE_CLEARANCE
        )
        self.support_drop = support_drop
        self.support_y_positions = [
            self.front_panel_y + (pos / 2.0) * usable for pos in p.hole_y_positions
        ]

        visible = set(p.visible_holes)
        holes: list[tuple[float, float]] = []
        for spec_index, (fz, bz) in enumerate(self.cut_specs):
            slope = (bz - fz) / usable
            ang = math.atan(slope)
            for hole_index, nominal_y in enumerate(self.support_y_positions):
                number = spec_index * len(self.support_y_positions) + hole_index + 1
                if number in visible:
                    y = nominal_y + support_drop * math.sin(ang)
                    z = (
                        bz
                        + slope * (nominal_y - self.back_panel_y)
                        - support_drop * math.cos(ang)
                    )
                    holes.append((y, z))
        # back corner holes #12 (back-bottom, 100 mm) and #14 (back-top, 15 mm)
        corner_x = (
            self.back_panel_y
            + self.back_thickness
            + CORNER_HOLE_GROOVE_CLEARANCE
            + HOLE_DIAMETER / 2.0
        )
        if 12 in visible:
            holes.append((corner_x, CORNER_HOLE_12_BOTTOM_DISTANCE))
        if 14 in visible:
            holes.append((corner_x, self.rack_height - CORNER_HOLE_TOP_BOTTOM_DISTANCE))
        self.holes = holes


def fmt(x: float) -> str:
    """Compact OpenSCAD-friendly number (no trailing zeros)."""
    x = round(float(x), 4)
    if float(x).is_integer():
        return str(int(x))
    return f"{x:.4f}".rstrip("0").rstrip(".")


def render_template(template: str, mapping: dict[str, str]) -> str:
    """Substitute ``{name}`` placeholders only.

    Unlike ``str.format``, literal ``{``/``}`` used by OpenSCAD blocks
    (modules, for/if bodies) pass through untouched.
    """
    return re.sub(r"\{(\w+)\}", lambda m: str(mapping[m.group(1)]), template)


# ===========================================================================
# .scad template — assembled from the rack geometry
# ===========================================================================

SCAD_TEMPLATE = """// ==========================================================
// PARAMETRIC SEROLOGICAL PIPETTE RACK — 3D MODEL
// Generated by make-it_3d.py
// ==========================================================
//
// COMMAND:
//   {command}
//
// PARAMETERS:
//   INNER_WIDTH   = {inner_width} mm      DEPTH (rack)    = {depth} mm
//   SIDE THICKNESS= {side_t} mm           BACK THICKNESS  = {back_t} mm
//   SHELF THICKNESS = {shelf_t} mm        GROOVE CUT WID  = {groove_w} mm
//   DROP          = {drop} mm             SIDE MARGIN     = {side_margin} mm (per end)
//   FIXED SHELVES = {fixed}               FLEXIBLE SHELVES= {flexible}
//   INTER-SHELF CLEARANCE = {inter} mm    FLEX OFFSET     = {offset} mm
//   BOTTOM CLEARANCE = {bottom} mm        TOP CLEARANCE   = {top} mm
//
// DERIVED:
//   RACK_WIDTH   = {rack_width} mm        RACK_HEIGHT   = {rack_height} mm
//   BACK PANEL W = {back_w} mm            SHELF WIDTH   = {shelf_w} mm
//   BLANK DEPTH  = {blank_depth} mm (side panel length = rack depth + 2 x side margin)
//   USABLE SPAN  = {usable} mm  (depth - 10)

// ---------------- display control ----------------
exploded_view   = false;
explode_x       = 40.0;      // right-side-panel slide when exploded
show_left_side  = true;
show_right_side = true;
show_back_panel = true;
show_shelves    = true;
view_alternative = false;    // view flexible shelf(ves) at the alternate position (2-in-1)

// ---------------- geometry (PREVIEW ONLY — values inlined) ----------------
// This file is for preview purposes, not engineering. All constants are baked
// in as literal numbers; the shelf/hole data in the lists below is exactly the
// design described in the header.

// [front_z, back_z] pairs (front_z = z of the groove centerline at the
// front panel plane; the shelf slopes down by `drop` toward the back)
cut_specs   = {cut_specs};
shelf_specs = {shelf_specs};
alt_specs   = {alt_specs};   // alternate position for flexible shelves (used when view_alternative)

// support hole [y, z] centers and back corner holes (numbered per the 2D layout)
support_holes = {support_holes};

function shelf_slope(fz, bz) = (bz - fz) / {usable};
function shelf_z_at_y(fz, bz, y)  = bz + shelf_slope(fz, bz) * (y - {back_panel_y});
function shelf_angle(fz, bz)      = atan(shelf_slope(fz, bz));
function shelf_len(fz, bz) = sqrt(pow({shelf_by} - {shelf_fy}, 2) + pow(shelf_slope(fz, bz) * ({shelf_by} - {shelf_fy}), 2));

// ==========================================================
// SIDE PANEL (drawn at the origin, mirrored for the right side)
// ==========================================================
module side_panel_blank() {
    difference() {
        cube([{side_t}, {blank_depth}, {rack_height}]);   // side panel, length = rack depth + 2 x side margin

        // sloped shelf grooves: primary shelves + flexible alternative slots.
        // The slot is centered on the 2D groove line so the 3D cut matches
        // the partial-depth groove drawn in the DXF. Groove 3.3 mm wide, cut
        // 2.0 mm past the front cut edge.
        for (i = [0 : len(cut_specs) - 1]) {
            s = cut_specs[i];
            fz = s[0];
            bz = s[1];
            y_start = -2.0;                                  // groove_overcut
            z_start = shelf_z_at_y(fz, bz, y_start);
            translate([{groove_dx}, y_start, z_start])
                rotate([shelf_angle(fz, bz), 0, 0])
                    cube([3.3, {back_panel_y} - y_start, {groove_w}],   // groove_depth, slot width
                         center = [false, false, true]);
        }

        // vertical back groove (back panel seats inside it)
        translate([{groove_dx}, {back_panel_y}, 4.0])          // back_groove_inset = 4.0
            cube([3.3, {back_t} + 0.5, {rack_height} - 8.0]);  // groove_depth 3.3, groove height = rack height - 2*4

        // support-rod holes (4.3 mm, axis along x through the panel)
        for (h = support_holes) {
            translate([{side_t} / 2.0, h[0], h[1]])
                rotate([0, 90, 0])
                    cylinder(d = 4.3, h = {side_t} + 2.0, $fn = 32);
        }
    }
}

// ==========================================================
// SHELF PANELS
// ==========================================================
// first {num_fixed} entries of shelf_specs are fixed shelves
function shelf_color(idx) =
    (idx >= {num_fixed})
    ? [1.0, 0.6, 0.1, 0.9]        // flexible shelves: amber
    : [0.0, 0.7, 0.8, 0.75];       // fixed shelves: teal

module shelf_panel(fz, bz, afz, abz, idx) {
    // view_alternative lifts the flexible shelf(ves) to the alternate position;
    // both groove slots are already cut in the side panels (2-in-1 option).
    use_fz = (idx >= {num_fixed} && view_alternative) ? afz : fz;
    use_bz = (idx >= {num_fixed} && view_alternative) ? abz : bz;
    translate([{shelf_x_pos}, {shelf_fy}, shelf_z_at_y(use_fz, use_bz, {shelf_fy})])
        rotate([shelf_angle(use_fz, use_bz), 0, 0])
            color(shelf_color(idx))
                cube([{shelf_w}, shelf_len(use_fz, use_bz), {shelf_t}],
                     center = [true, false, true]);
}

module all_shelves() {
    if (show_shelves) {
        for (i = [0 : len(shelf_specs) - 1]) {
            s = shelf_specs[i];
            a = alt_specs[i];
            shelf_panel(s[0], s[1], a[0], a[1], i);
        }
    }
}

// ==========================================================
// BACK PANEL (sits in the vertical back groove, 0.2 mm tolerance at the ends)
// ==========================================================
module back_panel() {
    translate([{groove_dx}, {back_panel_y}, 4.2])         // 4.0 inset + 0.2 clearance
        cube([{back_w}, {back_t}, {back_panel_height}]);
}

// ==========================================================
// ASSEMBLY
// ==========================================================
if (show_left_side) {
    color([0.55, 0.55, 0.55, 0.4])
        side_panel_blank();
}

if (show_right_side) {
    color([0.55, 0.55, 0.55, 0.4])
        translate([{rack_width} + (exploded_view ? explode_x : 0.0), 0, 0])
            mirror([1, 0, 0])
                side_panel_blank();
}

all_shelves();

if (show_back_panel) {
    color([1.0, 0.0, 1.0, 0.6])
        translate([0, exploded_view ? explode_x : 0.0, 0])
            back_panel();
}
"""


def quote_to_params(quote: ParsedQuote) -> RackParameters:
    """Map a parsed quote to RackParameters."""
    fixed_shelves, flexible_shelves = resolve_shelf_counts(quote)
    return RackParameters(
        inner_width=quote.inner_width,
        depth=quote.depth,
        drop=quote.drop,
        side_panel_thickness=quote.side_panel_thickness,
        back_panel_thickness=quote.back_panel_thickness,
        fixed_shelves=fixed_shelves,
        flexible_shelves=flexible_shelves,
        flexible_groove_offset=resolve_flexible_offset(quote),
        inter_shelf_clearance=quote.inter_shelf_clearance,
        shelf_thickness=quote.shelf_thickness,
        groove_cut_width=TECHNICAL_DEFAULTS["groove_cut_width"],
        bottom_clearance=quote.bottom_clearance,
        top_clearance=quote.top_clearance,
        side_margin=quote.side_margin,
    )


def generate(
    params: RackParameters,
    command: str,
    output_dir: str | pathlib.Path = OUTPUT_DIR_DEFAULT,
) -> pathlib.Path:
    """Render the parametric .scad for ``params`` and write it to disk.

    ``command`` is echoed in the file header so the model records how it was
    produced. Returns the path of the written file.
    """
    geo = RackGeometry(params)

    def pairs_to_scad(pairs):
        return (
            "[\n"
            + "".join(
                f"        [{', '.join(fmt(v) for v in pair)}],\n" for pair in pairs
            )
            + "    ]"
        )

    scad = render_template(
        SCAD_TEMPLATE,
        {
            "command": command,
            "inner_width": fmt(params.inner_width),
            "depth": fmt(params.depth),
            "side_t": fmt(params.side_panel_thickness),
            "back_t": fmt(params.back_panel_thickness),
            "shelf_t": fmt(params.shelf_thickness),
            "groove_w": fmt(params.groove_cut_width),
            "drop": fmt(params.drop),
            "side_margin": fmt(params.side_margin),
            "fixed": params.fixed_shelves,
            "flexible": params.flexible_shelves,
            "inter": fmt(params.inter_shelf_clearance),
            "offset": fmt(params.flexible_groove_offset),
            "bottom": fmt(params.bottom_clearance),
            "top": fmt(params.top_clearance),
            "rack_width": fmt(geo.rack_width),
            "rack_height": fmt(geo.rack_height),
            "back_w": fmt(geo.back_panel_width),
            "shelf_w": fmt(geo.shelf_width),
            "blank_depth": fmt(geo.blank_depth),
            "num_fixed": params.fixed_shelves,
            "usable": fmt(geo.back_panel_y - geo.front_panel_y),
            "back_panel_y": fmt(geo.back_panel_y),
            "groove_dx": fmt(geo.groove_dx),
            "shelf_fy": fmt(geo.shelf_fy),
            "shelf_by": fmt(geo.shelf_by),
            "shelf_x_pos": fmt(geo.groove_dx + 0.25),  # shelf_fit_clearance / 2
            "back_panel_height": fmt(geo.back_panel_height),
            "cut_specs": pairs_to_scad(geo.cut_specs),
            "shelf_specs": pairs_to_scad(geo.shelf_specs),
            "alt_specs": pairs_to_scad(geo.alt_specs),
            "support_holes": pairs_to_scad(geo.holes),
        },
    )

    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rack_3d.scad"
    out_path.write_text(scad)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map",
        action="store_true",
        help="Show the customer language → script parameter map",
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help="Show technical defaults applied to missing email fields",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR_DEFAULT,
        help=f"Where to write rack_3d.scad (default: {OUTPUT_DIR_DEFAULT})",
    )
    args = parser.parse_args()

    if args.map:
        print_parameter_map()
        return
    if args.defaults:
        print_technical_defaults()
        return

    text = read_quote_input().strip()
    if not text:
        print("No quote text provided.", file=sys.stderr)
        sys.exit(1)

    try:
        quote = parse_quote(text)
        params = quote_to_params(quote)
        out_path = generate(
            params, command="python make-it_3d.py < q.txt", output_dir=args.output_dir
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
