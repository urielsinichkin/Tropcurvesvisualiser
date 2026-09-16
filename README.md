# Tropical Curves Visualiser

A tool for working with **combinatorial types of rational (genus 0) plane
parametrized tropical curves**: input them, view their dual subdivision, edit
their slopes/markings/labels/colors, and derive new types by contracting edges
or resolving vertices — with edits propagating through the derivation tree.

The finished tool runs in the browser (Python core via Pyodide, responsive
SVG UI). This repository currently contains the **pure-Python core library**.

- Design of record: [`docs/DESIGN.md`](docs/DESIGN.md)
- Deferred features / decisions: [`docs/POSTPONED.md`](docs/POSTPONED.md)

## Core library (`tropcurves`)

Pure Python, exact integer arithmetic, no third-party runtime dependencies.

```python
from tropcurves import builders, newton_polygon, apply_two_ends_edit
from tropcurves.geometry import Vec2

c = builders.caterpillar_square()   # 4 ends, one bounded edge (dual: unit square)
print(c.edges["e"].vec)             # Vec2(1, 1) — solved by balancing
print(newton_polygon(c))            # the unit square, CCW from the origin

# Change one end's slope; a dependent end absorbs it to stay balanced:
apply_two_ends_edit(c, "a", Vec2(-2, -1), dependent_end_id="c")
```

## Web app

A browser UI lives in `web/` and runs the Python core in your browser via
Pyodide (no server, no install). Run it locally by serving the **repository
root** and opening the `web/` page:

```bash
python3 -m http.server 8000        # from the repo root
# then open http://localhost:8000/web/index.html
```

It loads the Pyodide runtime from a CDN on first visit, then reads the
`tropcurves` package straight from this repo. Your workspace autosaves in the
browser (localStorage); use **Export/Import** to move it between devices.

To publish it, enable GitHub Pages for this repository (served from the repo
root); the app is then at `…/web/index.html`.

### Deploying a change to the web app

Browsers cache these files aggressively, and a stale script paired with a fresh
`index.html` silently breaks newly added controls.

`app.js` handles itself: `index.html` loads it with a time-based token
(`app.js?t=<minute>`), so it can never be more than a minute stale — **even if
`index.html` itself was served from cache**. That matters because a fixed
`?v=N` lives *inside* `index.html`, so a cached page would keep asking for the
old script forever and never learn a new version exists.

When you deploy a change under `web/`, bump:

- `APP_VERSION` at the top of `web/app.js` (shown in the top bar, so you can
  confirm what's loaded), and
- the `?v=N` on the `<link rel="stylesheet">` tag, if you changed `styles.css`.

If the top-bar version is lower than expected, the browser is still on a cached
`index.html`; it will refresh on its own shortly, or you can force it by loading
the page with a throwaway query such as `?x=1`.

## Development

```bash
pip install -e ".[dev]"
pytest
```
