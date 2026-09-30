"""An owner tick holds only while the facts the owner saw are unchanged.

config/owner-confirmations.yaml binds each confirmation to a fingerprint of
the block's mastersheet facts. A re-fetch that changes an instructor or a link
must take the tick off and say so — never carry it onto facts nobody saw.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "gac", REPO / "pipeline" / "gen_acceptance_checklist.py")
gac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gac)

R = {"module_session": "S", "module_instructor": "I"}


def _block(instructor="Synthetic Primary", link="https://uplevel.example/1"):
    N = {"m": {"id": "m", "label": "Synthetic Module", "uplevel_link": link},
         "s": {"id": "s", "session_kind": "class", "uplevel_link": link},
         "i": {"id": "i", "label": instructor}}
    out = [{"rel": "S", "source": "m", "target": "s"},
           {"rel": "S", "source": "m", "target": "s", "attached_file": "deck.pptx"},
           {"rel": "I", "source": "m", "target": "i", "tier": "mastersheet",
            "instructor_role": "primary"},
           {"rel": "I", "source": "m", "target": "i", "tier": "legacy"},
           {"rel": "T", "source": "m", "target": "t"}]
    return N["m"], out, N


def _conf(fp):
    return {"SDx/1": {"module": "SDx/1", "fingerprint": fp, "origin": "hand",
                      "asserted_by": "Synthetic Owner", "asserted_at": "2026-09-30",
                      "evidence": "synthetic"}}


def test_an_unchanged_block_keeps_its_tick():
    fp = gac.mastersheet_fingerprint(*_block(), R)
    line, ticked = gac.owner_check("SDx/1", fp, _conf(fp))
    assert ticked and line.startswith("- [x]")


@pytest.mark.parametrize("change", [dict(instructor="Someone Else"),
                                    dict(link="https://uplevel.example/2")])
def test_a_changed_mastersheet_fact_takes_the_tick_off_and_says_so(change):
    fp = gac.mastersheet_fingerprint(*_block(), R)
    fp2 = gac.mastersheet_fingerprint(*_block(**change), R)
    line, ticked = gac.owner_check("SDx/1", fp2, _conf(fp))
    assert not ticked and line.startswith("- [ ]") and "CHANGED" in line


def test_non_mastersheet_edges_do_not_move_the_fingerprint():
    m, out, N = _block()
    fp = gac.mastersheet_fingerprint(m, out, N, R)
    out = out + [{"rel": "I", "source": "m", "target": "i", "tier": "legacy"},
                 {"rel": "S", "source": "m", "target": "s", "attached_file": "x.pdf"}]
    assert gac.mastersheet_fingerprint(m, out, N, R) == fp


def test_an_unconfirmed_module_is_unticked():
    assert gac.owner_check("SDx/9", "abc", {})[1] is False


@pytest.mark.parametrize("bad", ["origin: machine", "asserted_by: ''"])
def test_a_confirmation_must_be_a_complete_owner_fact(tmp_path, bad):
    key = bad.split(":")[0]
    entry = {"module": "SDx/1", "fingerprint": "f", "origin": "hand",
             "asserted_by": "O", "asserted_at": "2026-09-30", "evidence": "e"}
    entry[key] = bad.split(": ", 1)[1].strip("'")
    import yaml
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"confirmations": [entry]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        gac.load_confirmations(p)


def test_the_real_file_loads_and_every_tick_is_current():
    conf = gac.load_confirmations()
    assert conf, "no confirmations recorded"
    text = (REPO / "docs" / "ACCEPTANCE-CHECKLIST.md").read_text(encoding="utf-8")
    assert text.count("- [x] **Owner check**") == len(conf), (
        "a recorded confirmation no longer matches its block — the checklist "
        "says which; re-check it with the owner")
