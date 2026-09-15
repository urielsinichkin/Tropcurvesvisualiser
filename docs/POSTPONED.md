# Postponed features / deferred design decisions

A living list of things we consciously deferred to later versions, with enough
context to pick each up later. Scope for v1: **rational (genus 0) plane
parametrized tropical curves**.

## Mathematical scope

- **Positive genus curves.** v1 is genus 0 only (parametrizing graph is a tree).
  The data model and the balancing solver are being written to generalize, but
  UI, moduli, and validation assume trees for now.
- **Curves in higher-dimensional space (R^n, n > 2).** v1 is plane curves only
  (so the Newton-polygon / dual-subdivision duality applies).

## Slope editing (see interview §1)

- v1 only lets the user change the slopes of **ends**, via the "two ends"
  mechanism: the user picks one end to edit and one **dependent** end that is
  auto-recomputed as `u_dep = -sum of all other ends` to keep global balancing
  `sum w_i u_i = 0`; all other ends stay fixed. Internal edges are then derived
  by balancing.
- **Deferred:** general free-edge selection — let the user designate an
  arbitrary subset of edges as independent and solve the balancing linear system
  for the rest (well-posedness check for over/under-determined choices). The
  internal solve is being implemented as this general solver already; only the
  UI is restricted to "ends only" for now.
- **Deferred:** genuine interior-slope freedom at vertices of valency >= 4
  (where balancing does not uniquely determine incident directions).

## Subdivision / crossings (see interview §2)

- **Multiplicities** (lattice areas of cells, Mikhalkin weights) and any
  curve-counting: out of scope for now.
- **Chamber choice for display.** The combinatorial type (tree + slopes +
  markings) is the object of record; the dual subdivision is a display
  convenience. To draw it we pick an **arbitrary maximal-dimensional (generic)
  chamber** (generic edge lengths -> image -> read off crossings -> dual mixed
  subdivision). Deferred: canonical chamber selection, enumerating/among all
  chambers, or letting the user pick a chamber.
- **Regularity / coherence check** of an imported subdivision: deferred
  (optional). v1 builds the dual graph and validates the parametrizing curve is
  a tree, without checking the subdivision is regular.
- **Higher / multi-edge crossings** (three or more edge-images through one point,
  higher-weight edges crossing -> larger parallelograms / mixed cells): support
  the general mixed-subdivision data model, but rich handling deferred.

## Marked points (see interview §3)

- v1: marked points are **contracted ends** attached at vertices (invisible in
  the Newton polygon).
- **Deferred:** marked points sitting in the interior of an edge (would insert a
  2-valent vertex / change the graph model).

## Resolutions (see interview §4)

- Resolutions correspond to **adjacent maximal cells of the tropical moduli
  space**, not to triangulations of the dual polygon.
- v1: resolve **4-valent vertices only** (up to 3 resolutions = the 3 flag
  pairings; new bounded edge forced by balancing; may realize as an edge or a
  crossing).
- **Deferred:** resolution of vertices of valency >= 5 (richer: trivalent trees
  refining the vertex; count grows, and realizability/crossing structure with
  the plane slopes must be handled).

## Propagation (see interview §5)

- v1: a single per-type `follow_parent` flag = **all-or-nothing** transitive
  propagation.
- **Deferred:** selective propagation (per-element / per-attribute follow
  choices). The engine is built as a per-element/per-attribute rule set that
  currently resolves to all-or-nothing, so this can be enabled without rework.

## Platform / persistence (see interview §6, §7)

- v1: **Pyodide static site** (Python core in the browser, no server) with
  **browser autosave** (localStorage/IndexedDB) + JSON export/import.
- **Deferred:** cross-device cloud sync / backend; a hosted server option.
- **Deferred:** image (PNG/SVG) export of individual figures (JSON export is in
  v1; figure export can come later).
