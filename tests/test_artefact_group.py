"""Build/recording artefacts are COLLAPSED for display, never dropped.

Owner request (Animesh Kumar, 2026-09-30, checklist review part 1 §D):
.pyc, __pycache__, allure result/container/attachment JSON, *.log,
CACHEDIR.TAG, lastfailed/nodeids/stepwise and recording.conf collapse into
one "Build/recording artefacts (N)" group in the checklist and the panel.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import content_model as cm                          # noqa: E402

UUID = "c687143d-a13d-4f19-b9f7-04b0bc40ce24"


@pytest.mark.parametrize("name, path", [
    ("Fixtures.cpython-310-pytest-7.0.1.pyc", ""),
    ("conftest.py", "/x/__pycache__/conftest.py"),
    (f"{UUID}-result.json", ""), (f"{UUID}-container.json", ""),
    (f"{UUID}-attachment.txt", ""), (f"{UUID}-attachment", ""),
    ("run.log", ""), ("CACHEDIR.TAG", ""),
    ("lastfailed", ""), ("nodeids", ""), ("stepwise", ""),
    ("recording.conf", ""),
    ("/SD4: Test Engineering/Week 5/FM: RECORDED VIDEOS/03 pom demo/recording.conf", ""),
    ("history-trend.json", "/x/allure-report/history/history-trend.json"),
    ("README.md", "/x/.pytest_cache/README.md"),
])
def test_an_artefact_is_recognised(name, path):
    assert cm.is_build_artefact(name, path)


@pytest.mark.parametrize("name, path", [
    ("LoginPage.py", "/x/Assignment Review - Roland/LoginPage.py"),
    ("test_amazon_webpage_expected_title.py", ""),
    ("Recording Notes", ""), ("recording.config.md", ""),
    ("requirements.txt", ""), ("categories.json", "/x/app/categories.json"),
    ("Using console.log in tests.pptx", ""), ("Catalog", ""),
    ("my-result.json", ""), ("Email-attachment.pdf", ""),
    ("Speaker Notes - General Overview.docx", ""),
])
def test_real_content_is_not(name, path):
    assert not cm.is_build_artefact(name, path)


def test_the_client_carries_the_same_pattern():
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    assert "String.raw`" + cm.ARTEFACT_NAME + "`" in html, (
        "public/index.html's ARTEFACT_NAME has drifted from content_model's")
    body = html.split("function moduleChain(", 1)[1].split("\nfunction ", 1)[0]
    assert "isArtefact(" in body and "Build/recording artefacts (" in body


def test_the_checklist_collapses_and_still_links_every_one():
    text = (REPO / "docs" / "ACCEPTANCE-CHECKLIST.md").read_text(encoding="utf-8")
    groups = re.findall(r"<details><summary>Build/recording artefacts \((\d+)\)</summary>"
                        r"(.*?)</details>", text)
    assert groups, "no collapsed group in the checklist"
    for n, body in groups:
        assert body.count("](https://") == int(n), "a collapsed artefact lost its link"
    # nothing outside a group looks like an artefact
    outside = re.sub(r"<details>.*?</details>", "", text)
    assert not re.search(r"\[recording\.conf\]|\.pyc\]|\[CACHEDIR\.TAG\]", outside)
