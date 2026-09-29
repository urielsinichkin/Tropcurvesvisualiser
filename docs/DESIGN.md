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

What a readable picture needs, in order (`display_lengths` in `layout.py`):

1. **Edges of comparable drawn length.** Lengths used to be chosen in lattice
   units -- L = 1 along the primitive direction -- which draws an edge in
   direction (3,4) five times as long as one in direction (1,0); on a real
   workspace the drawn lengths spread 7-fold for no reason. Targets are now
   Euclidean: every edge of the underlying curve aims at drawn length 1, and an
   edge cut into pieces by interior markings shares that 1 between its pieces,
   so marking a point on an edge does not stretch it.
2. **Nothing touching that does not meet** -- `min_clearance`, the distance
   from the nearest vertex to anything it is not part of, as a fraction of the
   picture; ends are tested well past the length they are drawn at, and the
   measure is scale-invariant. Coincidences are artifacts of the lengths (a
   measure-zero set) so they can always be removed, except for a type with no
   generic embedding at all, which is reported as 0.
3. **Few crossings**, where lengths can avoid them -- for a type drawn on its
   own. Crossings forced by the slopes are real (they dualize to parallelograms).
4. **A derived type looks like its parent.** Vertices the two share keep their
   places as far as the lengths allow. Positions are linear in the lengths, so
   this is a least-squares fit, solved by coordinate descent with lengths
   bounded below (pure Python); the pull toward target lengths is only a
   tie-breaker, so it settles what the parent leaves free without ever
   competing with an exact match -- a contract-then-resolve that recreates an
   edge gives it a fresh id, and it must still land where the old one was. A
   child is held only to the clearance its parent achieved, so a type that
   differs from its parent by nothing but a marking comes out *identical*.
   Layouts are computed down the derivation tree and cached on the geometry of
   the whole chain.

When the fitted or even lengths are not good enough, a deterministic greedy
climb changes one edge at a time -- the change that lowers the cost most --
where the cost is a clearance shortfall plus crossings and unevenness (on its
own) or displacement from the parent (derived). A bottleneck is usually one or
two edges; changing only those keeps the rest even. Over random curves every
non-degenerate type reaches the clearance goal, the median has no crossings,
and the typical type keeps exactly even lengths.

The **dual subdivision** is built in the chamber that is drawn (falling back to
generic seeds if those lengths are not generic), so its parallelograms are the
crossings in the picture, and a derived type's subdivision stays like its
parent's too.

Still open: tuning the aspect ratio to the viewport, and making a type's own
picture stable across its own edits (an edit re-lays the type out from its
parent, or from scratch for a root).

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
colors). A hidden label is still placed -- after the shown ones, and clear of
everything -- so it can be revealed without landing on anything: while the
mouse is over its edge or marking, or by a tap on a touch screen (tap again, or
on empty space, to hide). Generous invisible targets make thin edges easy to
hit. Hidden labels stay out of a PNG copy.

The curve takes the full width of the middle column, with the dual subdivision
below it (on every screen size), and is taller on a desktop. It can be
**zoomed**: the mouse wheel (or a trackpad pinch) zooms about the pointer, two
fingers pinch-zoom on a touch screen, and once zoomed a drag moves around; -/+
buttons (desktop), a zoom level and **Fit** sit in the header. Zoom rewrites
the viewBox, so redraws of the same type (edits, painting) keep the view and
every click target lines up; a drag that moved the picture is never taken as a
click. At full view a downward wheel scrolls the page instead of being
swallowed. Choosing another type starts from the whole picture, and Copy
always copies the whole figure. The pictures in the Add marking, Contract edge
and Resolve vertex dialogs zoom the same way (`makeZoomable`, one controller
per picture, with the same level / -/+ / Fit controls beside the hint); each
dialog opens at full view, and re-highlighting after a pick keeps the zoom.

The **edit panel**'s parts (Type, Refined multiplicity, Actions, Markings,
Edges & ends) fold open and shut from their headings, and **Layout** on the
panel's title line opens a dialog to reorder them (drag and drop) and show or hide
each, with a reset. Like the other view preferences this is per browser
(`panelLayout` in the settings), never exported; a folded or hidden part is not
built, so the refined multiplicity is only computed while its part is open.

## 3. Operations

- **Contract edge** (bounded edges only): merge the two endpoints; dually erase
  the shared subdivision edge and merge the two cells. Ends/markings can't be
  contracted. The edge is picked on a picture of the curve by default (a list is
  one click away): with a mouse, hover highlights and a click contracts; on a
  touch screen a tap selects and a second tap, or the button, confirms. The same
  picture-first picker serves **Resolve** (the ringed vertices of valence >= 4;
  a click selects, the vertex's resolutions appear below, and the ticked side of
  a big vertex is coloured on the picture) and **Add marking** (a ringed vertex,
  or any point on an edge or end). The resolution itself is chosen from
  pictures too: at valence 4 each of the three is shown as the curve it
  produces, new edge highlighted, and clicked; beyond, the vertex's edges are
  clicked on the picture to choose a side, with the resulting curve drawn live
  (`Session.render_resolution` renders a resolution without creating it).
  Where pick targets overlap (a short edge lies inside its neighbours' wide hit
  strips) the pointer goes to the *nearest* target under it, not the one drawn
  last; a marking beats the edge it sits on, a vertex the edges meeting there.
- **Resolve a vertex** of valence `d >= 4`: split its flags into two groups,
  each with at least 2 (so neither new vertex is 2-valent, which would say
  nothing), joined by a new bounded edge whose direction is forced by balancing
  -- minus the sum of one group's outgoing vectors. A group forcing a zero
  vector is the crossing case: it realizes as a parallelogram rather than an
  edge and cannot be applied. At `d = 4` the only splits are 2+2, both new
  vertices come out trivalent, and the (up to 3) pairings are listed to choose
  from. Beyond that the count grows fast -- 10 splits at `d = 5`, 25 at `d = 6`
  -- so the UI has you tick one side instead, showing the forced edge as you go;
  the pieces may need resolving in turn.
- **Edit slopes**: the two-ends mechanism (2.2).
- **Add / remove markings**: contracted ends at a chosen vertex, or on a
  chosen edge/end (subdividing it as in 2.1). Subdividing an end keeps the
  original id and name on the unbounded piece, so slope editing and the Newton
  polygon are unaffected.
- **Rename**: ends, markings, edges (uniqueness enforced within a type).
- **Recolor**: any end, marking, or edge -- from its row in the side panel, or
  painted on the picture: **Paint** opens a color dialog (presets on a fine
  pointer too) with a "keep painting until I press Cancel" checkbox. Unticked,
  the next edge or marking clicked takes the color and painting ends; ticked,
  every click paints until **Cancel** (or Escape). A bar over the picture shows
  the color, a hint, **Change color** and **Cancel** in both modes. While
  painting, markings are drawn larger with a dashed ring so they are easy to
  hit, hovering previews the color, and copying the picture as PNG copies the
  plain figure. The last color and checkbox state are remembered.

### 3.1 Refined multiplicity (Goettsche-Schroeter)

For a trivalent curve,

    mult_q(C) = prod_{V unmarked} [mu(V)]_q^-  *  prod_{V marked} [mu(V)]_q^+,
    [a]_q^{+-} = (q^{a/2} +- q^{-a/2}) / (q^{1/2} +- q^{-1/2}),

with `mu(V)` the Mikhalkin multiplicity: the lattice area of the dual triangle,
computed as `|v1 ^ v2|` for two of the three outgoing vectors. A vertex counts
as **marked** when it carries a marking -- internally 4-valent with one
contracted end, i.e. a marked trivalent vertex.

A marking in the **interior of an edge** does not count: it is not a vertex of
the curve. Balancing makes its two edge directions opposite, so their wedge --
and `mu` -- vanishes, and the factor is 1, leaving the multiplicity exactly as
it was before the edge was subdivided. A bare two-valent vertex with no marking
is likewise a subdivision point rather than a vertex, and also contributes 1.
Neither comes from the formula, which at `a = 0` gives `[0]^- = 0` and
`[0]^+ = 2/(q^(1/2) + q^(-1/2))`; the factor is 1 identically.

It is **undefined** for anything else, and says which vertex and why: a vertex
of another shape, or a trivalent one whose dual triangle is degenerate.

Arithmetic is exact. Values are Laurent polynomials in `t = q^(1/2)` over the
integers, except that `[a]^+` for even `a` is genuinely not a polynomial;
nothing but `1 + t^2` can ever appear in a denominator, so a value is carried as
`num / (1 + t^2)^k` in lowest terms. Equality is then exact and addition closed
-- which is what lets a set of curves be searched for a **balanced split**: a
subset whose total multiplicity equals its complement's. Both halves are equal
exactly when one half is half of everything, so the search halves the total (no
subset can work if some coefficient is odd) and meets in the middle, `2^(n/2)`
work rather than `2^n`. A checkbox in the dialog (remembered per browser)
restricts the check to the values at q = 1, the Mikhalkin multiplicities
(`Session.balanced_split(ids, at_q_1=True)`, `balanced_split_numbers`): the
same search over plain numbers, so a set can balance there without its refined
multiplicities balancing.

The Multiplicity dialog lists the types in the types menu's order (each root
followed by its derived types, depth first; `typeTreeOrder`, also used by the
Export dialog) and nested the same way. Subtrees fold, starting as they are
folded in the menu; folding in the dialog does not change the menu. A folded
row shows how many types it hides and how many of those are ticked -- ticked
types count in the split check whether or not they are showing. Nothing is
ticked when the dialog opens.

### 3.2 Evaluation matrix

The cell of the moduli space of parametrized rational curves of a type has
coordinates `(x0, y0, l_e for each bounded edge e)`: the root vertex's image
and the edge lengths, so dimension `#bounded + 2`. An edge of length `l` with
direction vector `u` (weight included -- `Edge.vec`) moves its head by `l*u`
from its tail. The evaluation matrix (`evaluation.py`, `Session.evaluation_*`)
is the matrix of `n = #bounded + 2` linear functions on the cell, one row each,
columns `x0, y0` then the bounded edges by name:

- `x(m)`, `y(m)` of a marking: `x0` (or `y0`) plus `u_e` along the path from
  the root to the marking, `u_e` taken in the direction of travel;
- a cross ratio `cr(p1, p2, p3, p4)` of four markings/ends (markings being
  contracted ends), as in Tyomkin (arXiv:1509.07453): the signed length of the
  intersection of the oriented path `p1 -> p3` with the oriented path
  `p2 -> p4`, `+l_e` where they cross `e` the same way, `-l_e` otherwise.

The dialog (Actions -> Evaluation matrix...) picks the root from a list of the
markings, then the unmarked vertices (named by the edges meeting there), each
sorted by name, the first marking by default; the functions start as x and y
of every marking and can be added, removed, reordered (drag and drop) and changed. The matrix
can only be made with exactly `n` functions (and cross ratios of four different
legs). It shows with its exact determinant, and exports as text (Python,
Mathematica, Sage, MATLAB, LaTeX, plain) or as a PNG image with optional
row/column labels, copied to the clipboard for pasting into e.g. Notability
or downloaded. The choices for a type are kept for the session.

### 3.3 Reordering lists

Every list the user puts in order uses one component, `makeSortable` (with
`sortGrip` and `moveInArray`) in `app.js` -- the edit-panel layout and the
evaluation functions today, and any such list added later. Each item has a
grip (⠿); dragging it moves the item with a mouse, a finger or a pen alike
(Pointer Events, one code path). The grip has `touch-action: none`, so a touch
or Pencil drag starts at once while the rest of each row still scrolls; with a
mouse a row's empty space is a grip too. The item follows the pointer, the
others slide aside (a short FLIP animation), the scrolling area (dialog or
page) scrolls when the pointer nears its top or bottom edge, and Escape or a
cancelled touch puts the item back. The grip is a focusable button, and the
arrow keys move its item. The caller only supplies `onMove(from, to)`, which
moves the item in its data and redraws; the list element stays the same.

## 4. Derivation tree and propagation

Types form a **forest**: contraction/resolution create a **child** with a
recorded operation and an **element map** to the parent (child = parent minus
contracted edge; or parent plus new resolution edge(s)). A child records its
derivation as an ordered list of such steps, normally one.

- Each type has a **`follow_parent`** flag (default true).
- Propagation is **transitive**: an edit to a type flows to following children,
  then their following children, stopping at any `follow_parent = false`.
- A following child is **re-derived** by replaying its recorded operation on the
  updated parent. Edits to surviving mapped elements (rename/recolor/reslope)
  carry across the map; elements introduced by a resolution are local. If a
  replay no longer applies, the child is flagged **needs attention** rather than
  guessed. If an edit makes a child unbalanced/degenerate, it is flagged
  **invalid** with an explanation.
- A marking put on a derived type **survives** re-derivation. It is not in that
  type's recorded steps (the parent knows nothing about it), so a plain replay
  would drop it -- and a marking is part of the curve, not presentation: losing
  one turns a marked vertex into a plain one and changes the refined
  multiplicity. It is re-attached at the same vertex. Renames and recolors made
  directly on a derived type are still overwritten by the parent's, which is
  what all-or-nothing propagation means.
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
- **Deleting** a type (from its details panel, or the 🗑 on its row in the
  types list) by default removes that type and nothing else. It asks once to
  confirm (there is no undo), saying where the derived types will end up. The
  dialog has a checkbox, unticked by default, to delete every type derived from
  it as well, transitively (`Session.delete(id, with_descendants=True)`); the
  dialog's text and button then say how many go. Unticked, the derived types
  take its place: each moves up to the deleted type's
  parent with the deleted type's steps prepended to its own, so it is still the
  same derivation, expressed from one type further up, and edits keep reaching
  it. The children of a deleted **root** become roots, there being nothing left
  to derive them from; a `follow_parent = false` break is kept rather than
  silently healed. Edits made directly to the deleted type (a marking added on
  it, a recolor) are not part of any step, so a later re-derivation of its
  children no longer carries them.
- The propagation engine is built as a **per-element/per-attribute rule set**
  that currently resolves to all-or-nothing (the single flag), so **selective
  propagation** can be enabled later without reworking the model.

## 5. Workspace and persistence

- A **workspace** holds many types, the derivation forest, and presentation.
- **Continuous autosave** to browser storage (localStorage + IndexedDB), plus
  **JSON export/import** to move a workspace between devices.
- Import into a non-empty library asks whether to **add** the file's types or
  **replace** the library (`Session.load(text, append=True)` /
  `Workspace.merge`). Added types keep their derivations; one whose id is taken
  is renumbered with its links rewritten, and one whose name is taken gets a
  suffix ("root (2)"). Together with subset export this moves chosen types
  between workspaces.
- Export can save **a subset** of the types rather than all of them. A subset is
  not a truncation: it is the workspace with everything unselected deleted
  (section 4), so a kept type re-attaches to its nearest kept ancestor carrying
  the skipped steps in front of its own, or becomes a root when it has none.
  What comes out reads back as the same curves, still derived from one another
  wherever both ends were included. The dialog starts with nothing ticked (as
  does the Multiplicity dialog), lists the types in the types menu's order with
  the same folding as the Multiplicity dialog (`foldableTypeTree`, shared by
  both), and each type with derived types has a "Select with N derived" button
  that ticks it and its whole subtree (or, when all of those are ticked,
  unticks them). Folded types that are ticked are still exported.
- **Google Drive** (menu: Drive...): the library can be saved to and opened
  from the user's Drive. There is no server, so sign-in is Google Identity
  Services' browser token flow (client ID in `app.js`, registered for the
  `https://urielsinichkin.github.io` origin); the access token lasts about an
  hour and is kept in memory only. The scope is `drive.file`, so the app sees
  only files it created or was given. Saving writes the same JSON as Export to
  one Drive file that this browser remembers as *linked*, with its
  modification time when last saved or opened here; if the Drive copy changed
  since (another device), saving asks before overwriting (or saves a new file).
  Opening lists the app's files and goes through the same Add / Replace
  choice as Import; replacing links the library to that file. A 401 (expired
  session) asks the user to press again, which signs back in from the click.
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
  layout.py                 # display layout: even lengths, clearance, likeness to parent
  operations.py             # contract, resolve, edit slopes, markings, rename, color
  refined.py                # Goettsche-Schroeter refined multiplicity, balanced splits
  evaluation.py             # evaluation matrix: x/y of markings, cross ratios
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
- **P3 — Operations + propagation**: contract, resolve a vertex of any valence
  >= 4, markings,
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
  on their image, sized by valence; lengths chosen for clearance; the top bar's
  actions collapse behind a hamburger below 720px, since the row does not fit a
  phone; the types list folds: each type with derived types has a toggle and a
  count of what it hides, plus Collapse all / Expand all (view state, per
  browser, never exported). Selecting a type unfolds what it sits under, but a
  deliberate fold is otherwise left alone; the side panels resize by dragging
  the splitters between the columns (mouse, pen or finger; arrow keys when
  focused; double-click resets), remembered per browser and shrunk to fit a
  narrower window without losing the saved widths. Remaining:
  custom (graph/ends) curve entry, further aesthetic and a11y passes. Layout:
  even drawn lengths, fewer crossings, derived types drawn like their parents,
  the subdivision in the drawn chamber.]**

Each phase keeps the core independently testable before the GUI depends on it.
