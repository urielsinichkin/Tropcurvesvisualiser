// The in-app help: one entry per panel and dialog, shown by its "?" button
// (helpButton in app.js). Each gives the purpose and every feature and button,
// and links to the matching section of the full guide (help.html#anchor).
// Keep it in step with help.html when a panel or dialog changes.
const HELP = {
  topbar: {
    title: "The top bar",
    anchor: "topbar",
    html: `<p>The app's main menu. (On a narrow screen these buttons sit behind ☰.)</p>
      <ul>
        <li><b>New</b> — a new type: preset, drawn subdivision, or subdivision pasted as text.</li>
        <li><b>🎨 Display</b> — default colors, labels on/off, background.</li>
        <li><b>Multiplicity</b> — refined multiplicities of all types; search for balanced splits.</li>
        <li><b>Export…</b> — save the library, or a chosen part, as a JSON file.</li>
        <li><b>Import</b> — load a JSON file: add to the library or replace it.</li>
        <li><b>☁ Drive…</b> — save to / open from your Google Drive.</li>
        <li><b>⑂ GitHub…</b> — open a file from a GitHub repository and commit the library back (branches, history, pull requests).</li>
        <li><b>? Help</b> — this overview.</li>
        <li><i>saved …</i> — when the library was last saved in this browser (it saves itself); <i>v…</i> — the app version.</li>
      </ul>
      <p>Every panel and dialog has its own <b>?</b>.</p>`,
  },
  types: {
    title: "Types",
    anchor: "types",
    html: `<p>The library: every type, with derived types indented under the type they came from.</p>
      <ul>
        <li><b>Click</b> a type to show and edit it.</li>
        <li>Each row: name; counts of ends, bounded edges, markings; <i>follows</i> / <i>detached</i> for derived types; the first line of its description, if any (hover for all of it).</li>
        <li><b>▾ / ▸</b> folds a type's derived types; a folded row shows <b>+N</b>. <b>Collapse all / Expand all</b> folds everything. A dashed border means the selected type is folded inside.</li>
        <li><b>needs attention</b> — the type could not be rebuilt after its parent changed (open it and press <i>Try again</i>).</li>
        <li><b>🗑</b> — delete that type (asks first; its derived types move up unless you choose to delete them too).</li>
        <li><b>⠿</b> — drag to reorder a type among its siblings (its derived types come along; it never changes parent). Saved with the library.</li>
      </ul>`,
  },
  curve: {
    title: "The curve view",
    anchor: "curve",
    html: `<p>The selected type drawn as a plane tropical curve.</p>
      <ul>
        <li>Vertices are not drawn; <b>markings</b> are dots at their points, bigger where more edges meet. Labels name edges, ends and markings (weights above 1 as <i>(w4)</i>); hidden labels show on hover or tap.</li>
        <li>Derived types are drawn to look like their parent.</li>
        <li><b>Zoom</b>: mouse wheel, trackpad or two-finger pinch; drag to move around; <b>− / +</b>, the level, and <b>Fit</b> to see everything.</li>
        <li><b>🖌 Paint</b> — pick a color, then click edges and markings to color them (once, or until Cancel).</li>
        <li><b>Copy</b> — the whole curve as a PNG with a transparent background (downloaded if the clipboard refuses).</li>
        <li>A ⚠ line with <b>Try again</b> appears if the type needs attention.</li>
      </ul>`,
  },
  subdivision: {
    title: "Dual subdivision",
    anchor: "subdivision",
    html: `<p>The subdivision of the Newton polygon dual to the curve: a cell per vertex, an interior edge per bounded edge. It matches the lengths the curve is drawn with.</p>
      <ul>
        <li>Folded by default — click the heading to open it.</li>
        <li>Cell colors: green — a vertex; <b>violet — a marked vertex</b>; orange — a crossing (a parallelogram). A legend names those present.</li>
        <li><b>Copy</b> — the picture as a PNG including its background.</li>
        <li><b>subdivision text (debug)</b> — the cells as text, with <b>Copy</b>, reusable in <i>New → paste as text</i>.</li>
      </ul>`,
  },
  edit: {
    title: "The edit panel",
    anchor: "edit",
    html: `<p>Everything about the selected type. Click a part's heading to fold it (a folded part is not computed).</p>
      <ul>
        <li><b>Type</b> — name; description (free text, saved as you type); <i>follow parent</i> (whether the parent's edits reach this type); <b>Duplicate</b> (independent copy as a new root); <b>Delete…</b>.</li>
        <li><b>Refined multiplicity</b> — the Göttsche–Schroeter multiplicity, each vertex's factor and the value at q = 1 (or why it is undefined).</li>
        <li><b>Actions</b> — Edit end slope…, Add marking…, Contract edge…, Resolve vertex…, Evaluation matrix… (disabled, with the reason on hover, when not possible).</li>
        <li><b>Markings</b> / <b>Edges &amp; ends</b> — color (swatch, ▾ presets, hex code, ⟲ back to default) and name of each; ✕ removes a marking.</li>
        <li><b>⚙ Layout</b> — choose the order of these parts and which are shown.</li>
      </ul>
      <p>Edits pass on to derived types that follow this one.</p>`,
  },
  new: {
    title: "New type",
    anchor: "new",
    html: `<p>Create an independent root type.</p>
      <ul>
        <li><b>Tropical line (unit triangle)</b> — one vertex, three ends.</li>
        <li><b>4-ended curve (unit square)</b> — two vertices joined by a bounded edge.</li>
        <li><b>Draw a subdivision…</b> — draw cells on a lattice; the curve is its dual.</li>
        <li><b>or paste as text</b> — one cell per line, each a list of lattice points like <code>[[0,0],[1,0],[0,1]]</code>; then <b>Create from text</b>. Parallelograms become crossings.</li>
      </ul>`,
  },
  editor: {
    title: "Draw a subdivision",
    anchor: "editor",
    html: `<p>Draw a subdivision of a lattice polygon; the new type is the curve dual to it.</p>
      <ul>
        <li>Click lattice points to trace a cell; click the first point again or <b>Finish cell</b> to close it. Parallelograms (marked ×) become crossings.</li>
        <li><b>x … to …, y … to …</b> + <b>Resize grid</b> — the lattice window.</li>
        <li><b>Undo point</b>, <b>Delete last cell</b>, <b>Clear</b>.</li>
        <li><b>Create curve</b> — build the type. <b>Show text</b> — the cells as text, with <b>Copy</b>.</li>
      </ul>`,
  },
  settings: {
    title: "Display settings",
    anchor: "settings",
    html: `<p>How curves look, in this browser.</p>
      <ul>
        <li><b>Default edge / end / marking color</b> — for everything without its own color; <b>Use automatic</b> follows light/dark mode.</li>
        <li><b>Labels</b> — show edge and end names, marking names. Hidden ones still appear on hover or tap.</li>
        <li><b>Background</b> — the color behind the curve (pick, swatch, or <b>Use automatic</b>); the page adapts. Match it to where you paste pictures.</li>
      </ul>`,
  },
  export: {
    title: "Export",
    anchor: "export",
    html: `<p>Save types as a JSON file, to keep, share or move to another device.</p>
      <ul>
        <li>Nothing is ticked at first — tick the types to save.</li>
        <li><b>Select with N derived</b> — tick a type and everything derived from it (<b>Unselect…</b> when all are ticked).</li>
        <li><b>▾ / ▸</b>, <b>Collapse all</b> — fold subtrees; ticked types are saved even when folded.</li>
        <li><b>Select all</b> / <b>Select none</b>.</li>
        <li><b>Export</b> — download the file. A type whose parent is left out re-attaches to its nearest included ancestor (or becomes a root), so the file reads back as the same curves.</li>
      </ul>`,
  },
  import: {
    title: "Import",
    anchor: "import",
    html: `<p>The file holds types; your library already has some.</p>
      <ul>
        <li><b>Add to the library</b> — keep yours and add the file's types (with their derivations). Names already in use get a number, e.g. "root (2)".</li>
        <li><b>Replace the library</b> — discard the current types and load the file's.</li>
        <li><b>Close</b> — do neither.</li>
      </ul>`,
  },
  drive: {
    title: "Google Drive",
    anchor: "drive",
    html: `<p>Save the library to your Google Drive and open it there — also from other devices. The app sees only files it saved itself.</p>
      <ul>
        <li><b>Sign in with Google</b> — lasts about an hour or until reload; nothing is stored. <b>Sign out</b> ends it.</li>
        <li><b>Save as a new file</b> — under the name you type; this browser then links the library to it.</li>
        <li><b>Save to "name.json"</b> — update the linked file. If it changed elsewhere since, you are asked: <b>Overwrite it</b>, <b>Save as a new file instead</b>, or <b>Cancel</b>. <b>Unlink</b> forgets the link.</li>
        <li><b>Open from Drive</b> — the app's files, newest first: <b>Open</b> (then add to or replace the library), <b>Refresh</b>.</li>
      </ul>
      <p>If sign-in does not open, allow pop-ups for this site.</p>`,
  },
  github: {
    title: "GitHub",
    anchor: "github",
    html: `<p>Work on a workspace file in a GitHub repository: open it, then commit the library back to it.</p>
      <ul>
        <li><b>Access</b> — without a token, public repositories open read-only. To commit, paste a fine-grained personal access token for the repository (Contents: Read and write; Pull requests: Read and write for pull requests); <b>Save token</b> keeps it in this browser, <b>Forget token</b> removes it.</li>
        <li><b>Open from a repository</b> — <i>owner/repo</i> or a GitHub link, <b>Load</b>, pick the <b>Branch</b>, then <b>Open</b> a .json file (add to or replace the library). Replacing links the library to that file. <b>Commit as a new file</b> adds the library as a new file.</li>
        <li><b>Commit</b> — a message, then to the same branch (default) or <b>a new branch</b>. If the file changed on GitHub since you opened it, you choose: commit to a new branch, <b>Overwrite</b>, or <b>Cancel</b>.</li>
        <li><b>Open pull request</b> — from the linked branch into the default branch (offered after committing to a new branch).</li>
        <li><b>Show history</b> — the file's commits; <b>Open this version</b> loads an older one. <b>Unlink</b> forgets the link.</li>
      </ul>`,
  },
  paint: {
    title: "Paint",
    anchor: "paint",
    html: `<p>Color edges, ends and markings by clicking them on the curve.</p>
      <ul>
        <li>Choose a color (picker, presets or hex code).</li>
        <li><b>Keep painting until I press Cancel</b> — unticked: the next click paints and painting stops; ticked: every click paints.</li>
        <li><b>Start painting</b> — a bar above the curve shows the color, <b>Change color</b> and <b>Cancel</b> (Escape works too). Markings are enlarged and ringed; hovering previews.</li>
      </ul>`,
  },
  layout: {
    title: "Edit panel layout",
    anchor: "layout",
    html: `<p>Arrange the edit panel.</p>
      <ul>
        <li><b>Tick</b> the parts to show; untick to hide.</li>
        <li>Drag by <b>⠿</b> to reorder (or focus a grip and use ↑ / ↓).</li>
        <li><b>Reset to default</b> — original order, all shown and unfolded.</li>
      </ul>
      <p>Saved in this browser only.</p>`,
  },
  multiplicity: {
    title: "Refined multiplicities",
    anchor: "multiplicity",
    html: `<p>The refined multiplicity of every type, and a search for balanced splits.</p>
      <ul>
        <li>Types in the Types panel's order; <b>▾ / ▸</b> and <b>Collapse all</b> fold subtrees (a folded row shows how many it hides and how many are ticked).</li>
        <li>Nothing is ticked at first; tick types (or click names), or <b>Select all</b> / <b>Select none</b>. Undefined ones cannot be ticked.</li>
        <li><b>Check for a balanced split</b> — is there a way to split the ticked types into two groups with equal total multiplicity? Shows the groups and the common value (2 to 26 types).</li>
        <li><b>Find the maximal balanced sub-collections</b> — when the ticked set does not balance: every largest part of it that does, with its two halves; <b>Tick only these</b> selects one (up to 22 types).</li>
        <li><b>Only the values at q = 1 have to balance</b> — compare the classical multiplicities only.</li>
      </ul>`,
  },
  evaluation: {
    title: "Evaluation matrix",
    anchor: "evaluation",
    html: `<p>The matrix of n = #bounded edges + 2 evaluation functions on the type's cell, whose coordinates are the root's position (x0, y0) and the edge lengths (an edge of length ℓ and direction u, weight included, moves by ℓ·u).</p>
      <ul>
        <li><b>Root vertex</b> — markings first, then the other vertices (named by their edges).</li>
        <li><b>Evaluation functions</b> — x / y of a marking, or a cross ratio cr(p1,p2,p3,p4): the signed length of the intersection of the paths p1→p3 and p2→p4. <b>+ Add function</b>, <b>✕</b> remove, drag <b>⠿</b> to reorder, <b>Reset to x, y of every marking</b>.</li>
        <li><b>Column order</b> (folded) — drag the columns into order; <b>Default order</b>.</li>
        <li><b>Make the matrix</b> — only with exactly n functions. Shows the matrix and its exact determinant.</li>
        <li><b>As text</b> — Python, Mathematica, Sage, MATLAB, LaTeX or plain; <b>Copy text</b>. <b>As an image</b> — <b>Copy image</b> (for Notability etc.) or <b>Download image</b>, with or without labels.</li>
      </ul>`,
  },
  delete: {
    title: "Delete a type",
    anchor: "delete",
    html: `<p>Remove a type from the library. There is no undo.</p>
      <ul>
        <li>By default only this type goes: its derived types move up to its parent, keeping the same derivation (or become roots).</li>
        <li><b>Also delete all N derived types</b> — delete everything derived from it too, all the way down.</li>
        <li><b>Delete …</b> confirms; <b>Close</b> cancels.</li>
      </ul>`,
  },
  slope: {
    title: "Edit an end's slope",
    anchor: "slope",
    html: `<p>Change the direction of one end. Another end has to absorb the change to keep the curve balanced.</p>
      <ul>
        <li><b>end to edit</b> and its <b>new x</b>, <b>new y</b>.</li>
        <li><b>dependent end</b> — the one that changes to compensate (must be different).</li>
        <li><b>Apply</b> — the bounded edges are solved again; other ends stay; derived types follow.</li>
      </ul>`,
  },
  marking: {
    title: "Add a marking",
    anchor: "marking",
    html: `<p>Add a marked point (a contracted end) to this type.</p>
      <ul>
        <li>Pick a <b>ringed vertex</b> to put it there, or a point on an <b>edge or end</b> to split it and hang the marking on the new vertex.</li>
        <li>Mouse: hover shows, click adds. Touch: tap selects, tap again or <b>Add marking</b> adds.</li>
        <li><b>Name (optional)</b> — empty for an automatic name.</li>
        <li><b>Choose from a list instead</b> — pick from lists of vertices and edges. The picture zooms (wheel / pinch).</li>
      </ul>`,
  },
  contract: {
    title: "Contract an edge",
    anchor: "contract",
    html: `<p>Merge a bounded edge's endpoints into one vertex, making a new derived type that follows this one.</p>
      <ul>
        <li>Only bounded edges can be picked; the rest is faded.</li>
        <li>Mouse: hover shows, click contracts. Touch: tap selects, tap again or <b>Contract</b>.</li>
        <li><b>Choose from a list instead</b> — a list of the bounded edges. The picture zooms (wheel / pinch).</li>
      </ul>`,
  },
  resolve: {
    title: "Resolve a vertex",
    anchor: "resolve",
    html: `<p>Split a vertex of valence ≥ 4 in two, joined by a new edge forced by balancing — a new derived type.</p>
      <ul>
        <li>Pick a <b>ringed vertex</b> (or <b>Choose from a list instead</b>).</li>
        <li><b>Valence 4</b> — the three possible results as small pictures; hover to see the pairing, click to apply. <i>Crossing</i> ones cannot be applied.</li>
        <li><b>Valence 5+</b> — tick the edges for one side (or click them on the picture); a note and a preview show the result; <b>Resolve</b> applies it.</li>
        <li>The picture zooms (wheel / pinch).</li>
      </ul>`,
  },
};
