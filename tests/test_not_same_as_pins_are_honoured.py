"""`not_same_as` is a recorded human decision, and until now nothing read it.

16 pins across 6 people have been in config/people.yaml since the Karthika work,
carrying a stated guarantee — *"pinned so no fuzzy pass ever merges them"* — that
no code implemented. DECISIONS §A.7b instance 9, in a config file rather than a
document.

IT CURRENTLY SUPPRESSES NOTHING, and that is said out loud rather than left to be
assumed: no pinned pair is in the unresolved set today. A guard that never fires
is the shape this catalogue is full of, so the suppression is proved here by
construction instead of by waiting for it to matter.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PEOPLE = REPO / "config" / "people.yaml"


def _resolve_module():
    spec = importlib.util.spec_from_file_location(
        "np_resolve", REPO / "pipeline" / "03_resolve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _people() -> list[dict]:
    return yaml.safe_load(PEOPLE.read_text(encoding="utf-8"))["people"]


def test_the_pins_are_loaded_at_all():
    """The positive control: the decision reaches the code."""
    mod = _resolve_module()
    meta = {p["canonical"]: p for p in _people()}
    pins = mod.load_pins(meta)
    assert pins, "no not_same_as pins loaded — the recorded decisions are inert again"
    assert frozenset({"karthika s", "karthika pai"}) in pins


def test_a_pinned_pair_is_suppressed_not_proposed():
    """INJECTION PROOF, not a reading of the code path.

    The previous version of this test asserted that `load_pins` returned the
    pin — which proves the pin is LOADED and nothing about whether it does
    anything. That is exactly the claim `excluded-field` carried for months
    while matching two namespaces that never meet.

    So this calls the real `fuzzy_proposals` twice with the same inputs and
    asserts BOTH directions:

        without the pin  -> the pair IS proposed   (so the test is not vacuous)
        with the pin     -> the pair is suppressed (so the pin does the work)

    The first assertion is the one that matters. Without it, a change that broke
    fuzzy matching entirely would make this pass.
    """
    mod = _resolve_module()

    # A real pinned pair from people.yaml, close enough to be fuzzy-matched.
    canon, other = "Karthika S", "Karthika Saran"
    meta = {p["canonical"]: p for p in _people()}
    assert frozenset({canon.lower(), other.lower()}) in mod.load_pins(meta), \
        "the pair used by this test is no longer pinned in people.yaml"

    unpinned_run, suppressed = mod.fuzzy_proposals([other], [canon], set())
    pairs = {(p["candidate"], p["possible_match"]) for p in unpinned_run}
    assert (other, canon) in pairs, (
        f"WITHOUT the pin, {other!r} was not proposed against {canon!r} at all — "
        "this test would pass for the wrong reason, proving nothing about "
        "suppression. Has FUZZY_THRESHOLD changed?")
    assert not suppressed

    pinned_run, suppressed = mod.fuzzy_proposals(
        [other], [canon], {frozenset({canon.lower(), other.lower()})})
    pairs = {(p["candidate"], p["possible_match"]) for p in pinned_run}
    assert (other, canon) not in pairs, (
        "a pinned pair was proposed anyway — the recorded decision is inert")
    assert (other, canon) in suppressed, (
        "the pair was dropped but not REPORTED as suppressed; a silent "
        "suppression is indistinguishable from a pair the matcher never found")


def test_an_unpinned_near_match_is_still_proposed():
    """The suppression must not swallow real proposals.

    A pin list that quietly hid everything would also pass the test above.
    """
    mod = _resolve_module()
    meta = {p["canonical"]: p for p in _people()}
    proposed, suppressed = mod.fuzzy_proposals(
        ["Harsha"], ["Harsh Arora"], mod.load_pins(meta))
    assert any(p["possible_match"] == "Harsh Arora" for p in proposed), \
        "an unpinned near-match stopped being proposed"
    assert not suppressed


def test_no_alias_string_is_claimed_by_two_people():
    """The false-merge the alias map CAN make.

    Resolution is alias-only — a raw name not in the map becomes its own node —
    so the one way two people silently become one is a shared alias string.
    """
    seen: dict[str, list[str]] = {}
    for p in _people():
        for a in (p.get("aliases") or []) + [p["canonical"]]:
            seen.setdefault(str(a).strip().lower(), []).append(p["canonical"])
    clashes = {a: sorted(set(c)) for a, c in seen.items() if len(set(c)) > 1}
    assert not clashes, (
        f"alias strings claimed by more than one person: {clashes}. Every row "
        "carrying that string would resolve to whichever canonical won.")


def test_no_pin_is_contradicted_by_an_alias_list():
    """A pin says two people are different; an alias list saying otherwise
    would merge them anyway, and the pin would look like it was holding."""
    people = _people()
    alias_owner: dict[str, str] = {}
    for p in people:
        for a in (p.get("aliases") or []) + [p["canonical"]]:
            alias_owner[str(a).strip().lower()] = p["canonical"]

    contradictions = []
    for p in people:
        for other in (p.get("not_same_as") or []):
            owner = alias_owner.get(str(other).strip().lower())
            if owner == p["canonical"]:
                contradictions.append(f"{p['canonical']} pins {other!r} apart "
                                      "but also claims it as an alias")
    assert not contradictions, contradictions
