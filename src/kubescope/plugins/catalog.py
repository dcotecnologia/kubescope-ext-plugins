"""The Catalog page: the Helm charts of Artifact Hub as cards.

Each card names the chart, its version and repository, and has Learn
More (its page on Artifact Hub) and Install. Install runs nothing: as
with a Forward, it shows the `helm` commands for you to copy and run
yourself.
"""

import logging
from functools import partial
from typing import Any

from kubescope.sdk import translate

from kubescope.plugins.artifacthub import (
    CatalogError,
    Chart,
    Results,
    fetch_logo,
    search_charts,
)

logger = logging.getLogger(__name__)

COLUMNS = 3  # until the page has a width
CARD_WIDTH = 300  # pixels a card needs at least
GAP = 14
LOGO = 56  # pixels of a logo


def search(query: str, offset: int, filters: dict[str, Any] | None = None) -> Results:
    """Ask Artifact Hub, off the UI thread; whatever goes wrong is a
    `CatalogError`, so it is told and never lost."""
    try:
        return search_charts(query, offset, **(filters or {}))
    except CatalogError:
        raise
    except Exception as error:  # never let a thread die silently
        logger.exception("Catalog search failed")
        raise CatalogError(str(error)) from error


class InstallDialog:
    """The commands that install a chart, to copy and run in your terminal."""

    def __init__(self, parent: Any, chart: Chart, components: Any) -> None:
        note = components.label(
            translate(
                "InstallDialog",
                "KubeScope does not install charts. Copy these commands and run "
                "them in your terminal, with the context you want.",
            ),
            wrap=True,
        )
        self.box = components.command_box(chart.command, 110)
        copy = components.button(
            translate("InstallDialog", "Copy"),
            "primary",
            on_click=lambda: components.copy_text(chart.command),
        )
        close = components.button(translate("InstallDialog", "Close"))
        self.dialog = components.dialog(
            parent,
            translate("InstallDialog", "Install {name}").format(name=chart.name),
            components.column(note, self.box),
            [copy, close],
            width=620,
        )
        close.clicked.connect(self.dialog.accept)

    def exec(self) -> bool:
        return bool(self.dialog.exec())


class CatalogWidgets:
    """The widgets of the catalog page: the search, the filters and the
    cards."""

    def __init__(self, host: Any, components: Any) -> None:
        self.components = components
        self.searchInput = components.search_box(
            translate("PluginsCatalog", "Search the charts of Artifact Hub...")
        )
        self.searchInput.setMaximumWidth(520)
        self.searchButton = components.button(
            translate("PluginsCatalog", "Search"), "primary"
        )
        self.searchButton.setMinimumWidth(110)
        self.official = components.checkbox(translate("PluginsCatalog", "Official"))
        self.verified = components.checkbox(
            translate("PluginsCatalog", "Verified publisher")
        )
        self.cncf = components.checkbox(translate("PluginsCatalog", "CNCF"))
        self.sort = components.filter_select(
            [
                (translate("PluginsCatalog", "Most relevant"), "relevance"),
                (translate("PluginsCatalog", "Most starred"), "stars"),
                (translate("PluginsCatalog", "Recently updated"), "last_updated"),
            ]
        )
        self.statusLabel = components.label(variant="muted", wrap=True)
        self.cardsScroll, self.cardsGrid = components.grid_scroll(GAP)
        search = components.row(
            (self.searchInput, 1), self.searchButton, None, spacing=10
        )
        filters = components.row(
            components.label(translate("PluginsCatalog", "Show only"), "filter"),
            self.official,
            self.verified,
            self.cncf,
            None,
            components.label(translate("PluginsCatalog", "Sort by"), "filter"),
            self.sort,
            spacing=14,
        )
        components.page(
            host,
            filters=components.column(search, filters, spacing=12),
            notice=self.statusLabel,
            body=self.cardsScroll,
        )

    def filters(self) -> dict[str, Any]:
        """What the person chose to keep and how to order it, as the search
        takes it."""
        return {
            "official": self.official.isChecked(),
            "verified": self.verified.isChecked(),
            "cncf": self.cncf.isChecked(),
            "sort": self.sort.currentData(),
        }


class PluginsCatalog:
    """Drives the catalog page: searches, draws the cards, opens their
    links."""

    def __init__(self, ui: CatalogWidgets, host: Any, run_action: Any) -> None:
        self.ui = ui
        self.host = host
        self._run = run_action
        self.charts: list[Chart] | None = None
        self._busy = False  # a search is on its way
        self._asked = ""
        self.total = 0
        self._columns = COLUMNS
        self._logo_round = 0  # which search the logos on their way belong to
        self._logo_labels: dict[str, list[Any]] = {}
        self._images: dict[str, Any] = {}  # kept, so a redraw keeps the logos
        self._filters: dict[str, Any] = {}  # the ones of the search on the screen
        ui.searchButton.clicked.connect(self.search)
        ui.searchInput.returnPressed.connect(self.search)
        for box in (ui.official, ui.verified, ui.cncf):
            box.toggled.connect(self.search)  # a filter is a new search
        ui.sort.currentIndexChanged.connect(self.search)
        ui.components.on_resize(ui.cardsScroll.viewport(), self._resized)

    def _resized(self) -> None:
        """More cards side by side when the window gives room for them."""
        if self.charts and self._fit_columns() != self._columns:
            self.render()

    def _fit_columns(self) -> int:
        width = self.ui.cardsScroll.viewport().width()
        return max(1, (width + GAP) // (CARD_WIDTH + GAP))

    def ensure(self) -> None:
        """Load the first page the first time the catalog opens."""
        if self.charts is None and not self._busy:
            self.search()

    def search(self) -> None:
        self._asked = self.ui.searchInput.text().strip()
        self._filters = self.ui.filters()
        self.total = 0
        self.charts = None
        self._ask(0)

    def load_more(self) -> None:
        self._ask(len(self.charts or []))

    def _ask(self, offset: int) -> None:
        self.ui.statusLabel.setText(
            translate("PluginsCatalog", "Searching Artifact Hub...")
        )
        query = self._asked
        self._busy = True
        self._run(
            partial(search, query, offset, self._filters),
            lambda results: self._found(query, offset, results),
            on_error=lambda message: self._failed(query, message),
            quiet=True,
        )

    def _found(self, query: str, offset: int, results: Results) -> None:
        self._busy = False
        if query != self._asked:  # the person searched for something else since
            return
        if offset == 0:
            self.charts = []
        elif offset != len(self.charts or []):  # an answer to an earlier ask
            return
        self.charts = [*(self.charts or []), *results.charts]
        self.total = results.total
        self.ui.statusLabel.setText(
            translate("PluginsCatalog", "{shown} of {total} charts").format(
                shown=len(self.charts), total=self.total
            )
            if self.charts
            else translate("PluginsCatalog", "No chart matches that search")
        )
        self.render()
        self._load_logos()

    def _load_logos(self) -> None:
        """Read the logos of the charts shown, each off the UI thread; the
        logos of an earlier search, still on their way, are not wanted."""
        self._logo_round += 1
        wanted = [
            chart.logo_id
            for chart in self.charts or []
            if chart.logo_id and chart.logo_id not in self._images
        ]
        for logo_id in dict.fromkeys(wanted):
            self._run(
                partial(fetch_logo, logo_id),
                lambda data, logo_id=logo_id, round=self._logo_round: self._logo(
                    logo_id, data, round
                ),
                on_error=lambda _message: None,
                quiet=True,
            )

    def _logo(self, logo_id: str, data: bytes | None, round: int) -> None:
        if round != self._logo_round or not data:
            return
        image = self.ui.components.image(data, LOGO)
        if image is None:  # a format that cannot be drawn: no logo
            return
        self._images[logo_id] = image
        for label in self._logo_labels.get(logo_id, []):
            self.ui.components.set_image(label, image)

    def _failed(self, query: str, message: str) -> None:
        self._busy = False
        if query != self._asked:
            return
        self.ui.statusLabel.setText(
            translate("PluginsCatalog", "Could not reach Artifact Hub: {error}").format(
                error=message
            )
        )

    def render(self) -> None:
        grid = self.ui.cardsGrid
        components = self.ui.components
        self._logo_labels = {}
        while (item := grid.takeAt(0)) is not None:
            if widget := item.widget():
                widget.deleteLater()
        columns = self._columns = self._fit_columns()
        charts = self.charts or []
        for index, chart in enumerate(charts):
            components.grid_cell(
                grid, self._card(chart), index // columns, index % columns
            )
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        rows = (len(charts) + columns - 1) // columns
        if charts and len(charts) < self.total:
            more = components.button(
                translate("PluginsCatalog", "Load more"), on_click=self.load_more
            )
            components.grid_cell(grid, more, rows, 0, columns, center=True)
            rows += 1
        grid.setRowStretch(rows, 1)

    def _card(self, chart: Chart) -> Any:
        components = self.ui.components
        logo = components.image_label(LOGO)
        if chart.logo_id:
            self._logo_labels.setdefault(chart.logo_id, []).append(logo)
            if chart.logo_id in self._images:
                components.set_image(logo, self._images[chart.logo_id])
        marks = []
        official = translate("PluginsCatalog", "Official")
        cncf = translate("PluginsCatalog", "CNCF")
        for mark, text in (
            (chart.cncf, cncf),
            (chart.official, official),
            (chart.verified, translate("PluginsCatalog", "Verified publisher")),
        ):
            if mark:
                glyph = "\u2605" if text == official else "\u2713"
                badge = components.label("CNCF" if text == cncf else glyph, "mark")
                badge.setToolTip(text)
                marks.append(badge)
        install = components.button(
            translate("PluginsCatalog", "Install"),
            "primary",
            on_click=lambda: self.install(chart),
        )
        learn = components.button(
            translate("PluginsCatalog", "Learn More"),
            "link",
            on_click=lambda: self.learn_more(chart),
        )
        return components.card(
            components.row(logo, None, *marks),
            components.label(chart.name, "title", wrap=True),
            components.row(
                components.label(f"v{chart.version}" if chart.version else ""),
                None,
                components.label(chart.repository, align="right"),
            ),
            (components.label(chart.description, wrap=True, align="top-left"), 1),
            components.row(install, None, learn),
            name="pluginCard",
            min_height=190,
        )

    def install(self, chart: Chart) -> None:
        InstallDialog(self.host, chart, self.ui.components).exec()

    def learn_more(self, chart: Chart) -> None:
        self.ui.components.open_url(chart.link)
