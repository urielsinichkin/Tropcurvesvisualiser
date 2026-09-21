"""The browser loads the package file by file, so that list must stay honest."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_loader_lists_every_module_and_no_others():
    app = (ROOT / "web" / "app.js").read_text()
    block = re.search(r"const PKG_FILES = \[(.*?)\]", app, re.S)
    assert block, "PKG_FILES not found in web/app.js"
    listed = set(re.findall(r'"([^"]+\.py)"', block.group(1)))
    on_disk = {p.name for p in (ROOT / "tropcurves").glob("*.py")}
    assert listed == on_disk, (
        f"web/app.js is out of step with the package: "
        f"missing {sorted(on_disk - listed)}, stale {sorted(listed - on_disk)}"
    )
