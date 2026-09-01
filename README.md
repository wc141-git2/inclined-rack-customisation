# Inclined Multi-tier Rack, from-measurement-to-3d Workflow

This repository generates **a 3D model** for a custom inclined rack. The workflow goes from a customer-facing web configurator to a quote email to the 3D model — no manual re-entry of dimensions anywhere in between.

## Pipeline at a glance

```
ss-co0136_enriched.html        customer configurator (live preview + quote email draft)
        │  copy email draft, save as q.txt
        ▼
q.txt                          the hand-off file (plain text email)
        │  python make-it_3d.py < q.txt   (email in → .scad out)
        ▼
SCAD_DYNAMIC/                  rack_3d.scad → 3D model in OpenSCAD
```

## Files

| File | Role |
| --- | --- |
| `ss-co0136_enriched.html` | Customer-facing configurator. Adjusts width, depth, shelf slope, shelf counts/spacing, thicknesses, clearances, side margin, material. Updates a live side-view drawing and produces the quote email draft. |
| `q_example.txt` | A sample quote email — the exact hand-off format `make-it_3d.py` reads. |
| `make-it_3d.py` | Reads the quote text and directly writes `SCAD_DYNAMIC/rack_3d.scad`. Fully standalone — a single stdlib-only file. |
| `SCAD_DYNAMIC/` | Output directory (default): `rack_3d.scad` — the OpenSCAD 3D model. |
| `q_example_A.png` / `q_example_B.png` | Product photos used on the configurator page (two shelf-position assemblies). |

## Workflow (3 steps)

### 1. Configure the design in the HTML configurator

Open `ss-co0136_enriched.html` in a browser — no build step, no server. Every field updates the drawing and the quote live. The quote includes everything the generator needs — including the flexible-shelf levels and alternate position height.

### 2. Save the quote email to `q.txt`

Copy the email draft from the **quote text box** (the "DESIGN SUMMARY" email) and save it into `q.txt` in this folder. The file should contain only the email text — see `q_example.txt` for the format:

```
Hello Rytros Lab Solutions,

I would like to request a quote for a custom rack.

DESIGN SUMMARY
• Rack inner width: 120.0 mm
• Rack depth: 255.0 mm
• Rack height: 369.9 mm
• Shelf slope: 25.0 mm
• Shelf levels: 4
• Flexible shelf levels: 1
• Alternate shelf position height: 20.0 mm
• Fixed-shelf height: 95.0 mm
• Top clearance: 10.0 mm
• Material: Acrylic (PMMA)
• Side panel thickness: 6.0 mm
• Back panel thickness: 6.0 mm
• Shelf thickness: 5.0 mm
• Advanced: Side margin: 8.0 mm

Please confirm the design, lead time and price.

Kind regards
```

### 3. Generate the 3D model (one command)

```bash
python make-it_3d.py < q.txt        # → Wrote SCAD_DYNAMIC/rack_3d.scad
openscad SCAD_DYNAMIC/rack_3d.scad  # view
openscad -o SCAD_DYNAMIC/rack_3d.png --camera=0,150,220,55,0,25,500 SCAD_DYNAMIC/rack_3d.scad  # render a PNG
```

OpenSCAD is free and open source — see its [documentation](https://openscad.org/documentation.html) for installation, command-line options, and language reference.

`make-it_3d.py` is **completely standalone** — one stdlib-only file with no dependencies. It parses the quote email and writes a self-contained parametric OpenSCAD model of the assembled rack: left/right side panels with sloped shelf slots and the vertical back groove, sloped shelf panels, back panel, support and corner holes — all geometry derived from the quote's dimensions.

The generated `rack_3d.scad` is a **preview-only** model: every dimension is baked in as a literal number (no engineering variables), so it cannot silently drift from the quote. Only the display toggles remain editable in OpenSCAD — `show_*` / `exploded_view`, and `view_alternative` to view the flexible shelf at its alternate (2-in-1) position.

## Design rules (validated by the script)

- **Side margin** must be ≥ 8 mm (material added beyond the rack depth at **each** end, front and back — the physical outer depth is `rack depth + 2 × side margin`).
- **Bottom / top clearance** must be ≥ 10 mm.
- **Shelf slope**, **fixed-shelf height**, and **alternate shelf position height** must be > 0.
- At least one shelf level is required.

## Helpful commands

```bash
python make-it_3d.py --map       # customer wording → script parameter mapping
python make-it_3d.py --defaults  # technical defaults for missing email fields
python make-it_3d.py --help      # all options
```

## License

[MIT](LICENSE) — free to use, modify, and distribute.
