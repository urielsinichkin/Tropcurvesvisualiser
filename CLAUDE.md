# Working on this repository

A browser tool for combinatorial types of rational plane tropical curves:
Python core in `tropcurves/` (exact arithmetic, no SageMath), run in the
browser by Pyodide; the UI is `web/` (plain HTML/CSS/JS, no build step),
served by GitHub Pages at https://urielsinichkin.github.io/Tropcurvesvisualiser/web/.
`docs/DESIGN.md` is the design record -- keep it current with each change.

## Conventions

- Tests: `python3 -m pytest -q`. A new module in `tropcurves/` must also be
  listed in `PKG_FILES` in `web/app.js` (a test checks this).
- Bump `APP_VERSION` in `web/app.js` on every change to the web app, and the
  `styles.css?v=` number in `web/index.html` whenever `styles.css` changes.
- Reuse the shared UI pieces rather than building new ones:
  - **reordering any list: drag and drop with `makeSortable` / `sortGrip` /
    `moveInArray`** -- never up/down arrow buttons;
  - picking an edge/vertex/marking on a picture: `mountPicker` / `pickFrame`;
  - zoomable pictures: `makeZoomable`;
  - dialogs listing types: `typeTreeOrder` + `foldableTypeTree`;
  - loading a workspace file: `offerImport` (asks add or replace).
- Every UI change has to work with a mouse, touch (phone, iPad) and the iPad
  Pencil; check it headless in Chromium with Playwright (CDP touch events for
  touch, `Input.dispatchMouseEvent` with `pointerType: "pen"` for the pen).
