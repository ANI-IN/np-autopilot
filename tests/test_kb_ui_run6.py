"""Run 6 (B3): accessibility and layout across every KB screen.

  - WCAG AA contrast of the design tokens, computed from kb.css in both themes
    (no browser needed), and of the avatar hues in core.js.
  - In a real browser against eval/kb_dev_server.py, for every screen:
    no horizontal scroll at 1024px (light and dark), every visible control has
    an accessible name (screens, the record panel and page, the New record
    sheet, menus and dialogs), text cut off with "…" carries its full text as
    a tooltip, a visible focus indicator on every Tab stop, and no motion
    under prefers-reduced-motion.
  - No inline one-off styles left in the screens B3 owns (data-driven values
    such as a type colour or a bar's percentage are the only exceptions).

Browser parts need the playwright package and a local KB database (NP_TEST_DSN).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from kb_support import USERS, Client, dev_server, ensure_users, requires_kb, reset, token_for

REPO = Path(__file__).resolve().parent.parent
CSS = (REPO / "public" / "kb" / "kb.css").read_text(encoding="utf-8")
JS = REPO / "public" / "kb" / "js"


# ------------------------------------------------------------------ contrast (no browser)

def _tokens(block: str) -> dict:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


def _theme_tokens() -> dict:
    root = CSS[CSS.index(":root {"):CSS.index("@media (prefers-color-scheme: dark)")]
    dark_block = CSS[CSS.index(':root[data-theme="dark"] {'):]
    dark_block = dark_block[:dark_block.index("}")]
    light = _tokens(root)
    dark = dict(light)
    dark.update(_tokens(dark_block))
    return {"light": light, "dark": dark}


def _lum(h: str) -> float:
    h = h.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


#: Every text-on-surface pair the components use (foreground, background, where).
PAIRS = [
    ("text", "bg", "body text"), ("text-2", "bg", "secondary text"), ("text-3", "bg", "faint text"),
    ("text-3", "bg-subtle", "sidebar counts and group labels"), ("text-2", "bg-subtle", "sidebar links"),
    ("text-3", "surface-2", "faint text on a badge or skeleton row"), ("text-3", "surface-hover", "faint text on a hovered row"),
    ("text-2", "surface-2", "badge text"), ("text", "surface-2", "tokens"),
    ("accent-text", "bg", "links"), ("accent-text", "accent-soft", "accent badge, notice"), ("accent-text", "surface-hover", "link in a hovered row"),
    ("on-accent", "accent", "primary button, role badge P"), ("on-accent", "danger", "danger button, error toast"),
    ("bg", "text", "toast"), ("danger", "bg", "danger text"), ("danger", "danger-soft", "danger badge"),
    ("warn", "warn-soft", "warning badge"), ("ok", "ok-soft", "ok badge"),
]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_token_pairs_meet_wcag_aa(theme):
    t = _theme_tokens()[theme]
    low = [(fg, bg, where, round(contrast(t[fg], t[bg]), 2)) for fg, bg, where in PAIRS if contrast(t[fg], t[bg]) < 4.5]
    assert low == [], f"{theme}: pairs under 4.5:1 {low}"


def test_avatar_hues_carry_white_initials_at_aa():
    av = re.search(r"const AV = \[([^\]]+)\]", (JS / "core.js").read_text(encoding="utf-8")).group(1)
    hues = re.findall(r"#[0-9a-fA-F]{6}", av)
    assert hues
    assert all(contrast(h, "#ffffff") >= 4.5 for h in hues), [(h, round(contrast(h, "#ffffff"), 2)) for h in hues]


def test_one_radius_and_two_weights_in_the_stylesheet():
    rules = CSS[CSS.index("/* ------------------------------------------------------------------ base"):]
    radii = set(re.findall(r"border-radius:\s*([0-9.]+px)", rules))
    assert radii <= {"3px", "4px"}, radii          # small inner radii only; everything else is var(--radius)
    weights = set(re.findall(r"font-weight:\s*([0-9]+)", rules)) | set(re.findall(r"font:\s*([0-9]{3})\s", rules))
    assert weights <= {"400", "600"}, weights


#: Inline styles B3's screens may still set: values that come from data.
ALLOWED_INLINE = re.compile(r"style: '(--type:|--av:|--sw:|width:)'?")
B3_FILES = ["core.js", "detail.js", "form.js", "relpicker.js", "page.js"] + \
    [f"views/{p.name}" for p in (JS / "views").glob("*.js") if p.name not in ("graph.js", "people.js")]


@pytest.mark.parametrize("name", B3_FILES)
def test_no_one_off_inline_styles(name):
    src = (JS / name).read_text(encoding="utf-8")
    bad = [m.group(0) for m in re.finditer(r"style: '[^']*'", src) if not ALLOWED_INLINE.match(m.group(0))]
    assert bad == [], f"{name}: move these into kb.css classes: {bad}"


# ------------------------------------------------------------------ browser

pw = pytest.importorskip("playwright.sync_api", reason="kb ui: needs the playwright package")
expect = pw.expect

SCREENS = ["#/", "#/records", "#/programs", "#/courses", "#/resources", "#/outline", "#/graph", "#/teaching", "#/timeline",
           "#/activity", "#/quality", "#/approvals", "#/archived", "#/guide",
           "#/settings?tab=types", "#/settings?tab=relationships", "#/settings?tab=links", "#/settings?tab=tags",
           "#/settings?tab=members", "#/settings?tab=tokens", "#/settings?tab=templates", "#/settings?tab=sync"]

NAMES = """() => {
  const name = (e) => (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.getAttribute('title') || e.textContent || e.value || '').trim()
    || (e.id && document.querySelector('label[for="' + e.id + '"]') ? 'label' : '') || (e.closest('label') ? 'label' : '')
    || (e.getAttribute('placeholder') || '').trim();
  const bad = [];
  document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=option], [tabindex]:not([tabindex="-1"])').forEach((e) => {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) return;
    if (!name(e)) bad.push(e.tagName + '.' + (e.className && e.className.baseVal === undefined ? e.className : '') + ' ' + (e.getAttribute('data-testid') || ''));
  });
  return bad;
}"""

TRUNCATED = """() => {
  const bad = [];
  for (const e of document.querySelectorAll('#view *, #panel *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || !e.textContent.trim()) continue;
    const cs = getComputedStyle(e);
    const cut = (cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1)
      || (cs.webkitLineClamp && cs.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1);
    if (cut && !e.closest('[title]')) bad.push(e.tagName + '.' + e.className);
  }
  return bad;
}"""

HSCROLL = "() => document.documentElement.scrollWidth > window.innerWidth + 1 || document.getElementById('view').scrollWidth > document.getElementById('view').clientWidth + 1"


@pytest.fixture(scope="module")
def server():
    with dev_server() as base:
        yield base + "/kb/"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:                                              # noqa: BLE001
            b = p.chromium.launch(headless=True)
        yield b
        b.close()


CONTEXTS: list = []


@pytest.fixture(autouse=True)
def _close_pages():
    """Close each test's pages when it ends. Kept open until the module ended,
    every page kept polling the change feed, and by the last tests of a full
    run the shell could not finish loading within the timeout."""
    yield
    while CONTEXTS:
        CONTEXTS.pop().close()


@pytest.fixture(scope="module")
def data():
    """A small curriculum, created once for the module: a course with a long
    name, a module inside it with a link, a relationship, a tag."""
    ensure_users()
    reset()
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "A course with a rather long name that has to be cut off somewhere in a narrow column"})
    _, mod = ed.post("/api/kb/nodes", {"type": "module", "name": "Graphs and shortest paths", "parents": [course["id"]],
                                       "summary": "Breadth-first search, Dijkstra and the trade-offs between them, with practice problems.",
                                       "resources": [{"url": "https://example.com/slides", "title": "Graphs slides"}]})
    ed.post("/api/kb/nodes", {"type": "topic", "name": "Dijkstra"})
    yield {"course": course, "module": mod}
    while CONTEXTS:
        CONTEXTS.pop().close()
    reset()


def page_as(browser, base, role="admin", viewport=(1440, 900), scheme="light", reduced=False):
    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme,
                              reduced_motion="reduce" if reduced else "no-preference")
    CONTEXTS.append(ctx)
    sess = json.dumps({"access_token": token_for(USERS[role], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": f"kbtest-{role}@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)}); localStorage.removeItem('kb_draft_new_record');")
    page = ctx.new_page()
    errors: list = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(base)
    expect(page.get_by_test_id("whoami")).to_contain_text(role, timeout=20000)   # the first load warms the server
    page.errors = errors
    return page


def settle(page):
    page.wait_for_function("() => !document.querySelector('#view [aria-busy=true], #panel [aria-busy=true]')", timeout=20000)
    page.wait_for_timeout(300)


@requires_kb
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_no_horizontal_scroll_at_1024_on_any_screen(server, browser, data, scheme):
    page = page_as(browser, server, viewport=(1024, 768), scheme=scheme)
    over = []
    for route in SCREENS + ["#/r/" + data["module"]["id"], "#/records?open=" + data["module"]["id"]]:
        page.goto(server + route)
        settle(page)
        if page.evaluate(HSCROLL):
            over.append(route)
    assert over == [], over
    assert page.errors == []


@requires_kb
def test_every_control_has_an_accessible_name_and_cut_text_has_a_tooltip(server, browser, data):
    page = page_as(browser, server, viewport=(1280, 900))
    unnamed, cut = {}, {}
    for route in SCREENS + ["#/r/" + data["module"]["id"], "#/records?open=" + data["module"]["id"]]:
        page.goto(server + route)
        settle(page)
        if page.evaluate(NAMES):
            unnamed[route] = page.evaluate(NAMES)
        if page.evaluate(TRUNCATED):
            cut[route] = page.evaluate(TRUNCATED)
    assert unnamed == {}, unnamed
    assert cut == {}, cut
    assert page.errors == []


@requires_kb
def test_layers_name_every_control(server, browser, data):
    """The panel's tabs, its More menu, the New record sheet, the palette, the
    user menu, the View popover, the type editor and a relationship type dialog."""
    page = page_as(browser, server)
    mid = data["module"]["id"]
    found = {}
    steps = [("#/records?open=" + mid, "[data-testid=tab-links]"), ("#/records?open=" + mid, "[data-testid=tab-relationships]"),
             ("#/records?open=" + mid, "[data-testid=tab-history]"), ("#/records?open=" + mid, "[data-testid=more-actions]"),
             ("#/records", "[data-testid=new-record]"), ("#/", "[data-testid=open-palette]"), ("#/", "[data-testid=whoami]"),
             ("#/records", "[data-testid=view-options]"), ("#/settings?tab=types", "[data-testid=edit-type-module]"),
             ("#/settings?tab=relationships", "[data-testid=new-edge-type]")]
    for route, click in steps:
        page.goto(server + route)
        settle(page)
        page.locator(click).first.click()
        page.wait_for_timeout(500)
        bad = page.evaluate(NAMES)
        if bad:
            found[route + " " + click] = bad
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    assert found == {}, found
    assert page.errors == []


FOCUS = """() => {
  const e = document.activeElement;
  if (!e || e === document.body) return null;
  const cs = getComputedStyle(e);
  const ring = (cs.boxShadow && cs.boxShadow !== 'none') || (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0);
  // A table row shows its ring on its cells.
  const cell = e.tagName === 'TR' && e.firstElementChild && getComputedStyle(e.firstElementChild).boxShadow !== 'none';
  // A combobox shows its ring on its box (the input inside is borderless).
  const box = e.closest('.combo-box'); const combo = box && getComputedStyle(box).boxShadow !== 'none';
  // Tab past a date input's year lands on the browser's own calendar button (inside the
  // input's shadow tree, with the browser's focus ring): the input itself no longer matches :focus.
  const picker = e.matches('input[type=date]') && !e.matches(':focus');
  return {ok: !!(ring || cell || combo || picker), shadow: cs.boxShadow, outline: cs.outlineStyle, what: e.tagName + '.' + (typeof e.className === 'string' ? e.className : '') + ' ' + (e.getAttribute('data-testid') || e.getAttribute('aria-label') || '')};
}"""


@requires_kb
@pytest.mark.parametrize("route", ["#/", "#/records", "#/settings?tab=types", "#/activity", "#/archived", "#/quality"])
def test_every_tab_stop_shows_a_focus_ring(server, browser, data, route):
    page = page_as(browser, server)
    page.goto(server + route)
    settle(page)
    page.locator("body").click(position={"x": 1, "y": 1})
    missing = []
    for _ in range(40):
        page.keyboard.press("Tab")
        f = page.evaluate(FOCUS)
        if f and not f["ok"]:
            missing.append(f["what"] + ' ' + f['shadow'] + ' ' + f['outline'])
    assert missing == [], missing


@requires_kb
def test_keyboard_paths_search_filter_open_and_settings(server, browser, data):
    """Search (palette), open a record from it, open its More menu and leave it
    with Esc, move to Settings and its tabs by keyboard alone."""
    page = page_as(browser, server)
    page.keyboard.press("Control+k")
    page.keyboard.type("Graphs and")
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("panel-name")).to_have_text("Graphs and shortest paths")
    page.get_by_test_id("more-actions").focus()
    page.keyboard.press("Enter")
    expect(page.locator(".menu")).to_be_visible()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    expect(page.locator(".menu")).to_have_count(0)
    expect(page.get_by_test_id("more-actions")).to_be_focused()
    page.keyboard.press("Escape")                     # close the panel
    page.locator("#sidebar [data-nav=settings]").focus()
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("settings-tab-types")).to_be_visible()
    page.get_by_test_id("settings-tab-relationships").focus()
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("edge-types")).to_be_visible()
    # Activity filter by keyboard: the search box filters the list.
    page.goto(server + "#/activity")
    settle(page)
    page.get_by_test_id("activity-search").focus()
    page.keyboard.type("Dijkstra")
    page.wait_for_timeout(900)
    assert "q=Dijkstra" in page.evaluate("location.hash")
    assert page.errors == []


@requires_kb
def test_reduced_motion_turns_off_animation_and_transitions(server, browser, data):
    page = page_as(browser, server, reduced=True)
    page.goto(server + "#/records")
    settle(page)
    page.get_by_test_id("new-record").click()
    sheet = page.locator(".sheet")
    expect(sheet).to_be_visible()
    durations = page.evaluate("""() => {
      const s = getComputedStyle(document.querySelector('.sheet'));
      const b = getComputedStyle(document.querySelector('.btn'));
      const o = getComputedStyle(document.querySelector('.sheet-overlay'));
      return [s.animationDuration, o.animationDuration, b.transitionDuration, getComputedStyle(document.documentElement).getPropertyValue('--motion').trim()];
    }""")
    assert durations[0] in ("0s", "0ms") and durations[1] in ("0s", "0ms") and durations[2] in ("0s", "0ms"), durations
    assert durations[3].startswith("0ms"), durations
    assert page.errors == []


@requires_kb
def test_record_page_is_one_centred_column(server, browser, data):
    page = page_as(browser, server, viewport=(1920, 1000))
    page.goto(server + "#/r/" + data["module"]["id"])
    expect(page.get_by_test_id("panel-name")).to_be_visible()
    box = page.get_by_test_id("record-page").bounding_box()
    view = page.locator("#view").bounding_box()
    left, right = box["x"] - view["x"], (view["x"] + view["width"]) - (box["x"] + box["width"])
    assert abs(left - right) <= 2, (left, right)
    tabs = page.locator("[data-testid=record-page] .tabs").bounding_box()
    assert abs(tabs["x"] - box["x"]) <= 1 and abs(tabs["width"] - box["width"]) <= 1
    assert page.errors == []


@requires_kb
def test_selected_tab_does_not_shift_its_neighbours(server, browser, data):
    page = page_as(browser, server)
    page.goto(server + "#/settings?tab=types")
    settle(page)
    before = page.get_by_test_id("settings-tab-sync").bounding_box()["x"]
    page.get_by_test_id("settings-tab-links").click()
    settle(page)
    after = page.get_by_test_id("settings-tab-sync").bounding_box()["x"]
    assert abs(before - after) < 0.5, (before, after)
