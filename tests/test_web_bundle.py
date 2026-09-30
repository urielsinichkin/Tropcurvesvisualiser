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


def test_every_help_entry_points_at_a_guide_section():
    """Each "?" in the app has text in help-tips.js linking to help.html."""
    tips = (ROOT / "web" / "help-tips.js").read_text()
    guide = (ROOT / "web" / "help.html").read_text()
    ids = set(re.findall(r'id="([^"]+)"', guide))
    entries = re.findall(r'^  (\w+): \{\s*\n\s*title: "[^"]+",\s*\n\s*anchor: "([^"]+)",\s*\n\s*html: `',
                         tips, re.M)
    keys = re.findall(r"^  (\w+): \{", tips, re.M)
    assert len(entries) == len(keys), "every entry needs a title, an anchor and html"
    missing = [(k, a) for k, a in entries if a not in ids]
    assert not missing, f"help entries pointing nowhere in help.html: {missing}"
    toc = re.findall(r'href="#([^"]+)"', guide)
    assert all(t in ids for t in toc), "a contents link in help.html is broken"


def test_every_dialog_and_panel_has_help():
    """Dialogs go through dialogHead(helpKey, ...) or attachDialogHelp(key);
    each key must exist in help-tips.js."""
    app = (ROOT / "web" / "app.js").read_text()
    tips = (ROOT / "web" / "help-tips.js").read_text()
    keys = set(re.findall(r"^  (\w+): \{", tips, re.M))
    used = set(re.findall(r'dialogHead\("(\w+)"', app))
    used |= set(re.findall(r'attachDialogHelp\("(\w+)"\)', app))
    used |= set(re.findall(r'add\("[^"]+", "(\w+)"\)', app))
    used |= set(re.findall(r'toggleHelp\(top, "(\w+)"\)', app))
    assert used <= keys, f"help keys used but not written: {sorted(used - keys)}"
    unused = keys - used
    assert not unused, f"help written for nothing: {sorted(unused)}"
    # no dialog built without a key
    assert "dialogHead(title" not in app.replace("function dialogHead(helpKey, title", "")
