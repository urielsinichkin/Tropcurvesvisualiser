# Tropical Curves Visualiser — Design

A tool for working with **combinatorial types of rational (genus 0) plane
parametrized tropical curves**: input them, view their dual subdivision, edit
them, and derive new types by contracting edges or resolving vertices, with
edits propagating through the derivation tree.

This document is the living design of record. Deferred items live in
`POSTPONED.md`.

## 1. Scope (v1)

- Genus 0 (parametrizing graph is a **tree**), plane curves only.
- Arbitrary Newton polygon, possibly different per curve in one workspace.
- No multiplicities, no curve counting.

## 2. Core objects

### 2.1 Abstract curve (the "combinatorial type")

The object of record is **tree + slopes + markings**, plus presentation
(names, colors). Concretely:

- **Vertices** `V`: the internal nodes of the tree.
- **Flags / half-edges**: each edge end attached to a vertex. The tree is
  encoded by flags so we can talk about "the 4 flags at a vertex" (needed for
  resolution).
- **Bounded edges** `E`: connect two vertices. Each carries an integer
  **direction vector** `v = w*u` (`w = gcd(v)` the weight, `u` primitive),
  oriented; balancing uses the outgoing orientation at each endpoint.
- **Ends** (unbounded edges): attached to one vertex, carry an integer
  direction vector (weight * primitive), pointing outward.
- **Markings**: contracted ends (direction 0) attached at a vertex. Invisible
  in the Newton polygon. Named, colored. A marking can also be placed *on* an
  edge or end: the edge is subdivided at a new vertex, both pieces keeping the
  original direction vector, and the marking hangs at that vertex. The new
  vertex is then balanced automatically (the two pieces leave it in opposite
  directions and the marking contributes zero), the curve stays a tree, and the
  dual subdivision is unchanged.
- **Presentation**: every end, marking, and edge has a **name** (unique within
  the type) and a **display color**.

Genus 0 invariant: `#E = #V - 1` and the graph is connected and acyclic.

### 2.2 Balancing and the slope solver

At every vertex, `sum of (outgoing weight*primitive vectors) = 0`. Global
consequence: `sum over ends of w_i u_i = 0` (the Newton polygon closes).

The slope solver is written **generally**: given a partition of edges into
*free* (values fixed by the user) and *dependent* (solved), it solves the
per-vertex balancing linear system for the dependent edges and reports if the
partition is over/under-determined.

- **v1 exposes only "ends" editing** through the *two-ends* mechanism: the user
  designates one end to **edit** and one **dependent** end; on an edit, the
  dependent end is set to `u_dep = -(sum of all other ends)` to restore global
  balancing, all other ends stay fixed, and all bounded edges are re-derived by
  the solver (for a tree, prune cherries inward — always uniquely determined).
- Validation rejects edits that make the dependent end or any edge degenerate
  to the zero vector, with a clear message.

### 2.3 Newton polygon

Derived from the ends: each end `(w, u)` contributes a boundary edge of lattice
length `w` and outer normal `u`; sorting the end vectors by angle assembles the
convex polygon (well-defined because they sum to zero).

### 2.4 Dual subdivision (display only)

The combinatorial type is the record; the subdivision is a way to *show* it.
To build it we pick an **arbitrary maximal-dimensional (generic) chamber**:

1. Assign generic edge lengths (the layout pass, section 2.5).
2. Compute the image of the tree in the plane.
3. Find transverse crossings of edge images (4-valent points of the image).
4. Emit the **dual mixed subdivision** of the Newton polygon: trivalent
   image-vertices -> triangles, crossings -> parallelograms, higher-valent /
   higher-weight -> general (mixed) cells.

The subdivision model therefore allows triangles, parallelograms, and general
polygons/mixed cells — not just triangulations.

On **import from a subdivision** (secondary feature, no markings created): build
the dual graph (2-cells -> vertices, interior edges -> bounded edges, boundary
edges -> ends, direction = 90-degree primitive normal, weight = lattice length),
resolve parallelograms as crossings, and validate the **parametrizing curve is a
tree** (genus 0) — rather than rejecting interior vertices outright.

### 2.5 Layout (readability is a first-class goal)

Slopes are fixed, so only **lengths** and a root position are free. The layout
pass chooses positive lengths (and root) to make the drawing legible.

The first requirement is that the picture not *invent* structure: a vertex must
not sit on an edge it is not part of, and two vertices must not coincide. Unit
lengths are exactly the kind of special point where that happens (about a fifth
of random types put some vertex precisely on an unrelated edge), and it is
always an artifact -- the bad length vectors form a measure-zero set -- so
`readable_lengths` searches for a good one: score a candidate by
`min_clearance` (nearest vertex to anything it is not part of, as a fraction of
the picture's span) and take the first that clears the target, mild jitter
first, wider lengths only if that is not enough. Ends are scored well past the
length they are drawn at, so a gap cannot come from the ray being cut off; the
score is scale-invariant, so scaling the drawing cannot fake one either.

Two things are deliberately **not** targets. Crossings between edges are real
(they dualize to parallelograms) and no lengths remove them. And a type whose
flags at a vertex share a direction has no clear picture at all -- the same
degeneracy `build_subdivision` reports -- so there the search reports 0 rather
than pretending.

Still open: spreading vertices beyond mere clearance, label collisions, and
tuning the aspect ratio to the viewport. This same embedding machinery feeds the
generic-chamber subdivision.

**Drawing.** Vertices are not drawn: where edges meet already shows them.
Markings are drawn as discs exactly at their image, with radius proportional to
`valence - 2` of the vertex they hang from -- one unit for a marking in the
interior of an edge (internally a trivalent vertex), two for a marked trivalent
vertex, and so on.

**Labels.** Names are drawn last, against everything already in the picture. A
label that lands on an edge, a marking or another label reads as part of the
drawing rather than as a name for it, so each one is tried at a series of spots
near what it names -- along its edge on both sides, or around its disc --
nearest first, and takes the first that hits nothing and stays inside the panel.
A picture crowded enough to have no clear spot falls back to the least-bad one
rather than flinging the label somewhere unattached. Edge names and marking
names can each be turned off in Display settings (stored per browser, like the
colors).

## 3. Operations

- **Contract edge** (bounded edges only): merge the two endpoints; dually erase
  the shared subdivision edge and merge the two cells. Ends/markings can't be
  contracted.
- **Resolve a 4-valent vertex**: present the (up to 3) flag pairings 2+2. Each
  introduces a new bounded edge whose direction is forced by balancing; it may
  realize as a genuine edge or as a crossing (parallelogram); a pairing forcing
  a zero-vector edge is the crossing case. All valid pairings are shown, labeled
  embedded vs crossing. (>= 5-valent: deferred.)
- **Edit slopes**: the two-ends mechanism (2.2).
- **Add / remove markings**: contracted ends at a chosen vertex, or on a
  chosen edge/end (subdividing it as in 2.1). Subdividing an end keeps the
  original id and name on the unbounded piece, so slope editing and the Newton
  polygon are unaffected.
- **Rename**: ends, markings, edges (uniqueness enforced within a type).
- **Recolor**: any end, marking, or edge.

## 4. Derivation tree and propagation

Types form a **forest**: contraction/resolution create a **child** with a
recorded operation and an **element map** to the parent (child = parent minus
contracted edge; or parent plus new resolution edge(s)).

- Each type has a **`follow_parent`** flag (default true).
- Propagation is **transitive**: an edit to a type flows to following children,
  then their following children, stopping at any `follow_parent = false`.
- A following child is **re-derived** by replaying its recorded operation on the
  updated parent. Edits to surviving mapped elements (rename/recolor/reslope)
  carry across the map; elements introduced by a resolution are local. If a
  replay no longer applies, the child is flagged **needs attention** rather than
  guessed. If an edit makes a child unbalanced/degenerate, it is flagged
  **invalid** with an explanation.
- An operation names its elements **by id**, so an edit that changes *which* id
  sits at a flag has to update the records it invalidates. Only subdivision (a
  marking placed on an edge) does this, and it is precise: at the far endpoint
  the flag that was the edge is now the new stub, so a resolution there has that
  id substituted, and a contraction of the subdivided edge gains the new piece
  and contracts both -- the child keeps identifying the same two vertices, with
  the marking landing on the merged vertex. Fresh ids also avoid every id the
  derived types already claim, so a parent edit can never collide with a child's
  own resolution edge. A record that went stale anyway (a workspace saved before
  this) is repaired on replay when the correspondence is forced -- exactly one
  recorded flag gone and one unaccounted for -- and loading a workspace retries
  everything marked needs attention.
- The propagation engine is built as a **per-element/per-attribute rule set**
  that currently resolves to all-or-nothing (the single flag), so **selective
  propagation** can be enabled later without reworking the model.

## 5. Workspace and persistence

- A **workspace** holds many types, the derivation forest, and presentation.
- **Continuous autosave** to browser storage (localStorage + IndexedDB), plus
  one-click **JSON export/import** to move a workspace between devices.
- A versioned JSON schema is the single source of truth for save/load.

## 6. Architecture

- **Core (pure Python, exact integer arithmetic)** — no SageMath, and no
  `numpy` in the combinatorial/lattice core: lattice vectors are pairs of
  `int`, so gcd/primitive/balancing/Newton-polygon carry no floating-point
  error. Covers lattice geometry, the curve model, the balancing solver,
  operations, propagation, subdivision, and the JSON schema. `numpy` is reserved
  for the later float-based **layout** pass only. Fully unit-tested headless.
- **Runtime: Pyodide** — the same Python core runs in the browser; no server.
- **Frontend: HTML + JS + SVG**, responsive for phone / iPad / PC, visually
  polished. SVG for crisp scaling; a thin JS layer for interaction (menus, the
  resolution picker, color pickers, drag, autosave) calling into the Python core.
- **Deployable as a static site** (e.g. GitHub Pages).

## 7. Repo layout (planned)

```
tropcurves/                 # pure-Python core package
  geometry.py               # lattice vectors, gcd/primitive, hulls
  curve.py                  # abstract curve: vertices, flags, edges, ends, markings
  balancing.py              # general free/dependent slope solver
  newton.py                 # Newton polygon from ends
  subdivision.py            # generic-chamber dual mixed subdivision
  layout.py                 # readable length/embedding chooser
  operations.py             # contract, resolve, edit slopes, markings, rename, color
  workspace.py              # forest of types + propagation engine
  schema.py                 # versioned JSON (de)serialization
tests/                      # headless unit tests for the core
web/                        # static site (HTML/CSS/JS/SVG) + Pyodide bootstrap
docs/                       # DESIGN.md, POSTPONED.md
```

## 8. Phased roadmap

- **P1 — Core model + balancing** (headless, tested): curve data model, geometry,
  the two-ends slope solver, Newton polygon, JSON schema. **[done — 44 tests]**
- **P2 — Subdivision + layout**: readable layout, generic-chamber mixed
  subdivision, subdivision import. **[done: exact-rational embedding +
  generic-chamber mixed subdivision (triangles + parallelograms); subdivision
  *import* (`subdivision_import.py`) dualizes cells, opens parallelograms as
  crossings, validates a genus-0 tree, and is wired into the API/GUI (New → From
  subdivision); clearance-seeking length choice so no vertex is drawn on an edge
  it does not meet.]**
- **P3 — Operations + propagation**: contract, resolve-4-valent, markings,
  rename/color; the derivation forest and transitive propagation. **[done —
  operations + Workspace forest with transitive all-or-nothing propagation and
  needs-attention flagging; 65 tests total]**
- **P4 — Web GUI**: Pyodide bootstrap, SVG rendering of curve + subdivision,
  responsive layout, the resolution-picker menu and edit controls. **[done —
  `web/` static site; JSON `Session` facade; SVG curve + mixed-subdivision
  rendering (parallelograms highlighted); contract/resolve/slope/marking/
  rename/color controls; UI verified headless in Chromium against a mocked
  backend. Live Pyodide load requires CDN access (blocked in the build sandbox
  but fine in a normal browser).]**
- **P5 — Persistence**: continuous browser autosave, export/import. **[done —
  localStorage autosave after every edit + JSON export/import in `app.js`.]**
- **P6 — Polish**: aesthetics, mobile/tablet interaction, accessibility.
  **[done: visual click-to-draw subdivision editor (parallelograms auto-detected
  and shown as crossings) + subdivision text output for debug; theme-adaptive
  default edge/end/marking color (an unset color now renders as `var(--ink)`,
  fixing dark-background readability) with a Colors settings dialog to override
  the default and a per-element reset-to-default control; the dual-subdivision
  panel is collapsed by default per curve; vertices undrawn and markings drawn
  on their image, sized by valence; lengths chosen for clearance. Remaining:
  spreading beyond clearance and label-collision avoidance, custom (graph/ends)
  curve entry, further aesthetic and a11y passes.]**

Each phase keeps the core independently testable before the GUI depends on it.
