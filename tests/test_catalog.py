import struct
import zlib

import pytest
from kubescope.extensions import testing

from kubescope.plugins import catalog as module
from kubescope.plugins.artifacthub import CatalogError, Chart, Results
from kubescope.plugins.catalog import CatalogWidgets, InstallDialog, PluginsCatalog
from tests.conftest import FakeUi

CHART = Chart(
    "argo-cd", "argo", "10.18.0", "v3", "A Helm chart", True, True, True, "https://x"
)


def build(monkeypatch, results=None, error=None, logo=None):
    asked = []
    kept: list = []

    def search(query, offset=0, *_args, **filters):
        asked.append((query, offset))
        kept.append(filters)
        if error:
            raise error
        return results or Results([CHART], 1)

    monkeypatch.setattr(module, "search_charts", search)
    monkeypatch.setattr(module, "fetch_logo", lambda _id: logo)
    ui = FakeUi()
    host = ui.components.widget()
    widgets = CatalogWidgets(host, ui.components)
    catalog = PluginsCatalog(widgets, host, ui.run_action)
    catalog.kept = kept  # type: ignore[attr-defined]
    return catalog, widgets, asked


def test_opening_the_catalog_searches_once_and_draws_a_card_per_chart(
    monkeypatch,
) -> None:
    catalog, widgets, asked = build(monkeypatch)
    catalog.ensure()
    catalog.ensure()
    assert asked == [("", 0)]
    assert widgets.statusLabel.text() == "1 of 1 charts"
    assert widgets.cardsGrid.count() == 1


def test_a_search_asks_for_what_was_typed_and_more_loads_the_next_page(
    monkeypatch,
) -> None:
    catalog, widgets, asked = build(monkeypatch, Results([CHART], 2))
    widgets.searchInput.setText("argo")
    catalog.search()
    assert widgets.cardsGrid.count() == 2  # one card and the "Load more" button
    catalog.load_more()
    assert asked == [("argo", 0), ("argo", 1)]


def test_a_failure_and_an_empty_answer_are_said(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch, error=CatalogError("offline"))
    catalog.search()
    assert "offline" in widgets.statusLabel.text()
    catalog, widgets, _asked = build(monkeypatch, Results([], 0))
    catalog.search()
    assert widgets.statusLabel.text() == "No chart matches that search"


def test_an_answer_to_an_earlier_search_is_ignored(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch)
    catalog._asked = "new"
    catalog._found("old", 0, Results([CHART], 1))
    catalog._failed("old", "x")
    assert catalog.charts is None and widgets.statusLabel.text() == ""


def test_the_install_dialog_shows_the_commands_to_copy() -> None:
    ui = FakeUi()
    dialog = InstallDialog(None, CHART, ui.components)
    assert dialog.box.toPlainText() == CHART.command
    assert dialog.dialog.windowTitle() == f"Install {CHART.name}"


def png() -> bytes:
    """A 1x1 PNG, made by hand."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


def test_a_search_that_fails_in_a_way_nobody_expected_is_still_told(
    monkeypatch,
) -> None:
    def boom(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "search_charts", boom)
    with pytest.raises(CatalogError, match="boom"):
        module.search("x", 0)

    def offline(*_args):
        raise CatalogError("offline")

    monkeypatch.setattr(module, "search_charts", offline)
    with pytest.raises(CatalogError, match="offline"):
        module.search("x", 0)


def test_more_cards_fit_side_by_side_when_the_window_grows(monkeypatch) -> None:
    catalog, _widgets, _asked = build(monkeypatch)
    catalog.search()
    catalog._columns = 99  # what was drawn for another width

    catalog._resized()
    assert catalog._columns == catalog._fit_columns()
    columns = catalog._columns
    catalog._resized()  # the same width: kept
    assert catalog._columns == columns


def test_an_answer_for_a_page_that_is_not_the_next_one_is_ignored(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch, Results([CHART], 5))
    catalog.search()
    shown = widgets.statusLabel.text()

    catalog._found("", 7, Results([CHART], 5))  # asked for offset 7, has only one

    assert widgets.statusLabel.text() == shown and len(catalog.charts or []) == 1


def test_a_logo_is_drawn_in_the_cards_that_wait_for_it(monkeypatch) -> None:
    with_logo = Chart(
        "loki", "grafana", "1", "", "d", False, False, False, "https://x", "ab"
    )
    catalog, widgets, _asked = build(monkeypatch, Results([with_logo], 1), logo=png())
    catalog.search()  # the logo is read at once by the fake action
    labels = catalog._logo_labels["ab"]
    assert "ab" in catalog._images and not labels[0].pixmap().isNull()

    catalog.render()  # drawn again: the logo is kept
    assert not catalog._logo_labels["ab"][0].pixmap().isNull()

    catalog._logo("zz", b"not an image", catalog._logo_round)  # cannot be drawn
    assert "zz" not in catalog._images
    catalog._logo("ab", None, catalog._logo_round)  # one that cannot be read
    catalog._logo("ab", png(), catalog._logo_round - 1)  # of an earlier search
    assert widgets.cardsGrid.count() >= 1


def test_the_install_button_shows_the_commands_and_learn_more_opens_the_page(
    monkeypatch,
) -> None:
    catalog, _widgets, _asked = build(monkeypatch)
    shown: list[object] = []
    opened: list[str] = []
    monkeypatch.setattr(module.InstallDialog, "exec", lambda self: shown.append(self))
    monkeypatch.setattr(catalog.ui.components, "open_url", opened.append)

    catalog.install(CHART)
    catalog.learn_more(CHART)

    assert len(shown) == 1 and opened == [CHART.link]


def test_a_filter_or_a_new_order_is_a_new_search_and_more_keeps_it(monkeypatch) -> None:
    catalog, widgets, asked = build(monkeypatch, Results([CHART], 5))
    catalog.search()
    assert catalog.kept[-1] == {  # type: ignore[attr-defined]
        "official": False,
        "verified": False,
        "cncf": False,
        "sort": "relevance",
    }

    widgets.official.setChecked(True)  # a click on a filter searches again
    widgets.cncf.setChecked(True)
    widgets.sort.setCurrentIndex(widgets.sort.findData("stars"))
    assert len(asked) == 4
    assert catalog.kept[-1] == {  # type: ignore[attr-defined]
        "official": True,
        "verified": False,
        "cncf": True,
        "sort": "stars",
    }

    widgets.verified.blockSignals(True)  # not to search, to see the next page
    widgets.verified.setChecked(True)
    catalog.load_more()
    assert asked[-1][1] == 1  # the next page
    last = catalog.kept[-1]  # type: ignore[attr-defined]
    assert last["verified"] is False  # of the search on the screen


def test_the_search_asks_artifact_hub_for_the_filters_and_the_order(
    monkeypatch,
) -> None:
    from kubescope.plugins import artifacthub

    urls: list[str] = []

    class Answer:
        headers = {"Pagination-Total-Count": "1"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"packages": []}'

    def urlopen(request, timeout=0):
        urls.append(request.full_url)
        return Answer()

    monkeypatch.setattr(artifacthub.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(artifacthub.json, "load", lambda response: {"packages": []})
    artifacthub.search_charts("loki", 0, 20, True, True, True, "stars")
    artifacthub.search_charts("loki", 0, 20, sort="no such order")
    assert "official=true" in urls[0] and "verified_publisher=true" in urls[0]
    assert "cncf=true" in urls[0] and "sort=stars" in urls[0]
    assert "official" not in urls[1] and "sort=relevance" in urls[1]


def test_the_install_dialog_says_whether_it_was_accepted(monkeypatch) -> None:
    dialog = InstallDialog(None, CHART, FakeUi().components)
    testing.answer_dialogs(monkeypatch, lambda _dialog: 1)
    assert dialog.exec() is True
    testing.answer_dialogs(monkeypatch, lambda _dialog: 0)
    assert dialog.exec() is False
