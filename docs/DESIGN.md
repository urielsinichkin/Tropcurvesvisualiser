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
  in the Newton polygon. Named, colored.
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
pass chooses positive lengths (and root) to make the drawing legible:

- spread vertices, avoid near-coincident vertices/edges and label collisions,
- keep a pleasant aspect ratio and margins for the current viewport,
- keep genuine crossings visually clear.

Implemented as a constrained optimization / heuristic over the length vector;
this same embedding feeds the generic-chamber subdivision.

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
- **Add / remove markings**: contracted ends at a chosen vertex.
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
  subdivision, subdivision import.
- **P3 — Operations + propagation**: contract, resolve-4-valent, markings,
  rename/color; the derivation forest and transitive propagation.
- **P4 — Web GUI**: Pyodide bootstrap, SVG rendering of curve + subdivision,
  responsive layout, the resolution-picker menu and edit controls.
- **P5 — Persistence**: continuous browser autosave, export/import.
- **P6 — Polish**: aesthetics, mobile/tablet interaction, accessibility.

Each phase keeps the core independently testable before the GUI depends on it.
