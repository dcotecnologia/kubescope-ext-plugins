from PySide6.QtWidgets import QWidget

from kubescope.plugins import catalog as module
from kubescope.plugins.artifacthub import CatalogError, Chart, Results
from kubescope.plugins.catalog import CatalogWidgets, InstallDialog, PluginsCatalog

CHART = Chart(
    "argo-cd", "argo", "10.18.0", "v3", "A Helm chart", True, True, True, "https://x"
)


def build(monkeypatch, results=None, error=None):
    asked = []

    def search(query, offset=0, *_args):
        asked.append((query, offset))
        if error:
            raise error
        return results or Results([CHART], 1)

    monkeypatch.setattr(module, "search_charts", search)
    monkeypatch.setattr(module, "fetch_logo", lambda _id: None)
    host = QWidget()
    widgets = CatalogWidgets(host)
    return PluginsCatalog(widgets, host), widgets, asked


def wait(catalog):
    worker = catalog._worker
    if worker is not None:
        worker.wait()
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.processEvents()


def test_opening_the_catalog_searches_once_and_draws_a_card_per_chart(
    monkeypatch,
) -> None:
    catalog, widgets, asked = build(monkeypatch)
    catalog.ensure()
    wait(catalog)
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
    wait(catalog)
    assert widgets.cardsGrid.count() == 2  # one card and the "Load more" button
    catalog.load_more()
    wait(catalog)
    assert asked == [("argo", 0), ("argo", 1)]


def test_a_failure_and_an_empty_answer_are_said(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch, error=CatalogError("offline"))
    catalog.search()
    wait(catalog)
    assert "offline" in widgets.statusLabel.text()
    catalog, widgets, _asked = build(monkeypatch, Results([], 0))
    catalog.search()
    wait(catalog)
    assert widgets.statusLabel.text() == "No chart matches that search"


def test_an_answer_to_an_earlier_search_is_ignored(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch)
    catalog._asked = "new"
    catalog._found("old", 0, Results([CHART], 1))
    catalog._failed("old", "x")
    assert catalog.charts is None and widgets.statusLabel.text() == ""


def test_the_install_dialog_shows_the_commands_to_copy(monkeypatch) -> None:
    from PySide6.QtWidgets import QPlainTextEdit

    dialog = InstallDialog(None, CHART)
    box = dialog.findChild(QPlainTextEdit)
    assert box is not None and box.toPlainText() == CHART.command


def png() -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # type: ignore[call-overload]
    return bytes(data.data())


def test_a_search_that_fails_in_a_way_nobody_expected_is_still_told(
    monkeypatch,
) -> None:
    worker = module.SearchWorker("x", 0)
    told: list[tuple] = []
    worker.failed.connect(lambda query, message: told.append((query, message)))

    def boom(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "search_charts", boom)
    worker.run()

    assert told == [("x", "boom")]


def test_the_logos_are_read_one_by_one_until_the_search_changes(monkeypatch) -> None:
    worker = module.LogoWorker(["a", "b", "c"])
    got: list[str] = []
    worker.logo.connect(lambda logo_id, _data: got.append(logo_id))
    monkeypatch.setattr(
        module, "fetch_logo", lambda logo_id: None if logo_id == "b" else b"x"
    )

    worker.run()
    assert got == ["a", "c"]  # one that cannot be read has no logo

    got.clear()
    monkeypatch.setattr(worker, "isInterruptionRequested", lambda: True)
    worker.run()
    assert got == []


def test_more_cards_fit_side_by_side_when_the_window_grows(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch)
    catalog.search()
    wait(catalog)
    catalog._columns = 99  # what was drawn for another width

    from PySide6.QtCore import QEvent

    viewport = widgets.cardsScroll.viewport()
    assert catalog.eventFilter(viewport, QEvent(QEvent.Type.Resize)) is False
    assert catalog._columns == catalog._fit_columns()
    catalog.eventFilter(viewport, QEvent(QEvent.Type.Resize))  # the same width: kept
    assert catalog.eventFilter(viewport, QEvent(QEvent.Type.Show)) is False


def test_an_answer_for_a_page_that_is_not_the_next_one_is_ignored(monkeypatch) -> None:
    catalog, widgets, _asked = build(monkeypatch, Results([CHART], 5))
    catalog.search()
    wait(catalog)
    shown = widgets.statusLabel.text()

    catalog._found("", 7, Results([CHART], 5))  # asked for offset 7, has only one

    assert widgets.statusLabel.text() == shown and len(catalog.charts or []) == 1


def test_a_logo_is_drawn_in_the_cards_that_wait_for_it(monkeypatch) -> None:
    with_logo = Chart(
        "loki", "grafana", "1", "", "d", False, False, False, "https://x", "ab"
    )
    catalog, widgets, _asked = build(monkeypatch, Results([with_logo], 1))
    catalog.search()
    wait(catalog)
    labels = catalog._logo_labels["ab"]
    assert labels and labels[0].pixmap().isNull()

    catalog._logo("ab", b"not an image")  # a format Qt cannot draw: no logo
    assert "ab" not in catalog._pixmaps
    catalog._logo("ab", png())
    assert "ab" in catalog._pixmaps and not labels[0].pixmap().isNull()

    catalog.render()  # drawn again: the logo is kept
    assert not catalog._logo_labels["ab"][0].pixmap().isNull()
    catalog.search()  # a new search drops the logos still on their way
    catalog._logos = module.LogoWorker([], catalog)
    catalog._logos.logo.connect(catalog._logo)  # as one on its way always is
    catalog._load_logos()
    wait(catalog)
    catalog._logos_done(module.LogoWorker([], catalog))
    assert widgets.cardsGrid.count() >= 1


def test_the_install_button_shows_the_commands_and_learn_more_opens_the_page(
    monkeypatch,
) -> None:
    catalog, _widgets, _asked = build(monkeypatch)
    shown: list[object] = []
    opened: list[str] = []
    monkeypatch.setattr(module.InstallDialog, "exec", lambda self: shown.append(self))
    monkeypatch.setattr(
        module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )

    catalog.install(CHART)
    catalog.learn_more(CHART)

    assert len(shown) == 1 and opened == [CHART.link]
