"""The Installed page: the add-ons of the cluster (Amazon EKS, Azure, Google
Cloud) and its Helm releases, with their chart, app and latest versions.

It is laid out like the lists of the app: a filter bar, the summary, the
table and a footer. The app lists them
(`ctx.cluster.get_resources(context, None, "Addon")`); the page asks for
the latest version of each, filters by origin and, in the write mode,
updates one with the command it shows first.
"""

import logging
from collections.abc import Callable
from typing import Any

from kubescope.sdk import CONTEXT_CHANGED, THEME_CHANGED, WRITE_MODE_CHANGED
from kubescope.sdk.errors import ClusterError
from kubescope.sdk.models import natural_key
from PySide6.QtCore import QCoreApplication, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kubescope.plugins import latest, updates
from kubescope.plugins.badge import BADGE_ROLE, BadgeDelegate
from kubescope.plugins.check_header import CheckHeader
from kubescope.plugins.update_dialog import AKS_KIND, PluginUpdateDialog

logger = logging.getLogger(__name__)

GKE_KIND = "GkeAddon"
POLL_SECONDS = 30  # how often the page looks again while it is shown
ROW_HEIGHT = 46  # as the rows of the lists of the app
FIELD_HEIGHT = 38
TEXT_COLOR = "#242a33"
UPDATE_COLOR = "#3220a0"
NAME, STATUS, CHART, APP, LATEST, SOURCE, UPDATED, AGE = range(8)
WIDTHS = (258, 110, 130, 90, 100, 90, 100)  # as the lists of the app

_GOOD = {"NORMAL", "ACTIVE", "DEPLOYED", "AVAILABLE", "RUNNING", "ENABLED"}
_WARNING = {
    "WARNING",
    "CREATING",
    "UPDATING",
    "DELETING",
    "UNINSTALLING",
    "MODIFYING",
    "UPGRADING",
    "STARTING",
    "STOPPING",
}
_BAD = ("FAIL", "ERROR", "DEGRADED", "INCOMPATIBLE")


def origin_of(kind: str) -> str:
    """`helm` for a Helm release, `cluster` for what the cloud lists."""
    return "helm" if kind == "HelmRelease" else "cluster"


def badge_colors(status: str) -> tuple[str, str]:
    """The text and fill colors of the badge of a status: green when fine,
    amber while it changes, red when it failed."""
    word = status.upper()
    if any(bad in word for bad in _BAD):
        return "#a33d45", "#fce9ea"
    if word in _GOOD:
        return "#176b58", "#e5f4eb"
    if word in _WARNING or word.startswith("PENDING"):
        return "#985415", "#fff2de"
    return "#505963", "#eff1f3"


def status_text(value: str) -> str:
    """A status as the clouds and Helm word it, in the interface language; a
    word that is not known stays as it came."""
    known = {
        "ACTIVE": QCoreApplication.translate("InstalledPage", "Active"),
        "CREATING": QCoreApplication.translate("InstalledPage", "Creating"),
        "UPDATING": QCoreApplication.translate("InstalledPage", "Updating"),
        "DELETING": QCoreApplication.translate("InstalledPage", "Deleting"),
        "DEGRADED": QCoreApplication.translate("InstalledPage", "Degraded"),
        "FAILED": QCoreApplication.translate("InstalledPage", "Failed"),
        "CREATE_FAILED": QCoreApplication.translate("InstalledPage", "Creation failed"),
        "UPDATE_FAILED": QCoreApplication.translate("InstalledPage", "Update failed"),
        "DELETE_FAILED": QCoreApplication.translate("InstalledPage", "Deletion failed"),
        "PENDING": QCoreApplication.translate("InstalledPage", "Pending"),
        "DEPLOYED": QCoreApplication.translate("InstalledPage", "Deployed"),
        "SUPERSEDED": QCoreApplication.translate("InstalledPage", "Superseded"),
        "UNINSTALLED": QCoreApplication.translate("InstalledPage", "Uninstalled"),
        "UNINSTALLING": QCoreApplication.translate("InstalledPage", "Uninstalling"),
        "PENDING_INSTALL": QCoreApplication.translate(
            "InstalledPage", "Pending install"
        ),
        "PENDING_UPGRADE": QCoreApplication.translate(
            "InstalledPage", "Pending upgrade"
        ),
        "PENDING_ROLLBACK": QCoreApplication.translate(
            "InstalledPage", "Pending rollback"
        ),
    }
    key = value.strip().upper().replace(" ", "_").replace("-", "_")
    return known.get(key, value)


def update_icon(color: str) -> QIcon:
    """The arrow that says a newer version is out."""
    size = 18 * 3  # drawn three times larger so the edges stay smooth
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(27, 42, 27, 12)  # an arrow rising from a base, as the app draws it
    painter.drawLine(16, 23, 27, 12)
    painter.drawLine(38, 23, 27, 12)
    painter.drawLine(12, 46, 42, 46)
    painter.end()
    return QIcon(
        pixmap.scaled(
            QSize(18, 18),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def info_icon(color: str) -> QIcon:
    """A circle with an i, for the button of the details."""
    size = 18 * 3
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(7, 7, 40, 40)
    painter.drawLine(27, 25, 27, 38)
    painter.drawPoint(27, 17)
    painter.end()
    return QIcon(
        pixmap.scaled(
            QSize(18, 18),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def trash_icon(color: str) -> QIcon:
    """A bin, for the button that uninstalls."""
    size = 18 * 3
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(10, 16, 44, 16)  # the lid
    painter.drawLine(21, 16, 21, 10)
    painter.drawLine(33, 16, 33, 10)
    painter.drawLine(21, 10, 33, 10)
    painter.drawLine(14, 16, 17, 44)  # the body
    painter.drawLine(40, 16, 37, 44)
    painter.drawLine(17, 44, 37, 44)
    painter.end()
    return QIcon(
        pixmap.scaled(
            QSize(18, 18),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def switch_button(text: str, tip: str) -> QPushButton:
    """The Aa and .* switches of a search box, like the app's."""
    button = QPushButton(text)
    button.setCheckable(True)
    button.setToolTip(tip)
    button.setFixedSize(FIELD_HEIGHT, FIELD_HEIGHT)
    button.setProperty("variant", "secondary")
    return button


class InstalledPage(QWidget):
    def __init__(self, ctx: Any) -> None:
        super().__init__()
        self.ctx = ctx
        self.rows: list[Any] = []
        self._sort: tuple[int, Qt.SortOrder] | None = None
        self._checked: set[tuple[str, str, str]] = set()
        self.newest: dict[tuple[str, str, str], str] = {}
        self._loading = False

        self.origin = QComboBox()
        self.origin.setProperty("variant", "filter")
        self.origin.setMinimumSize(170, FIELD_HEIGHT)
        self.origin.addItem(
            QCoreApplication.translate("InstalledPage", "All origins"), ""
        )
        self.origin.addItem("Helm", "helm")
        self.origin.addItem(
            QCoreApplication.translate("InstalledPage", "Cluster"), "cluster"
        )
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setMinimumSize(240, FIELD_HEIGHT)
        self.search.setMaximumWidth(300)
        self.search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.search.setPlaceholderText(
            QCoreApplication.translate("InstalledPage", "Search all columns...")
        )
        self.search.setClearButtonEnabled(True)
        self.case_button = switch_button(
            "Aa", QCoreApplication.translate("InstalledPage", "Match case")
        )
        self.regex_button = switch_button(
            ".*", QCoreApplication.translate("InstalledPage", "Regular expression")
        )
        self.summary = QLabel()
        self.summary.setObjectName("summaryLabel")
        self.table = QTableWidget(0, len(WIDTHS) + 1)
        self.table.setProperty("variant", "data")
        self.check_header = CheckHeader(self.table, self.themed)
        self.table.setHorizontalHeader(self.check_header)
        self.check_header.toggled.connect(self._check_all)
        self.check_header.setSectionsClickable(True)
        self.check_header.sectionClicked.connect(self._sort_by)
        self._filling = False
        self.table.setHorizontalHeaderLabels(
            [
                QCoreApplication.translate("InstalledPage", "NAME"),
                QCoreApplication.translate("InstalledPage", "STATUS"),
                QCoreApplication.translate("InstalledPage", "CHART"),
                QCoreApplication.translate("InstalledPage", "APP"),
                QCoreApplication.translate("InstalledPage", "LATEST"),
                QCoreApplication.translate("InstalledPage", "SOURCE"),
                QCoreApplication.translate("InstalledPage", "LAST UPDATE"),
                QCoreApplication.translate("InstalledPage", "AGE"),
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)  # the rows draw their own divider
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for column, width in enumerate(WIDTHS):
            self.table.setColumnWidth(column, width)
        self.table.setItemDelegate(BadgeDelegate(self.table))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.footer = QLabel()
        self.footer.setProperty("variant", "muted")
        note = QLabel(
            QCoreApplication.translate(
                "InstalledPage", "Data fetched from the cluster API"
            )
        )
        note.setProperty("variant", "muted")
        self.notice = QLabel()
        self.notice.setProperty("variant", "muted")
        self.notice.setWordWrap(True)

        filters = QHBoxLayout()
        filters.setSpacing(12)
        label = QLabel(QCoreApplication.translate("InstalledPage", "ORIGIN"))
        label.setObjectName("filterLabel")
        filters.addWidget(label)
        filters.addWidget(self.origin)
        filters.addWidget(self.search)
        filters.addWidget(self.case_button)
        filters.addWidget(self.regex_button)
        filters.addStretch(1)
        summary = QHBoxLayout()
        summary.addWidget(self.summary)
        summary.addStretch(1)
        self.details_button = self._action_button(
            QCoreApplication.translate("InstalledPage", "Details"),
            info_icon(self.themed(UPDATE_COLOR)),
            self.show_details,
        )
        self.update_button = self._action_button(
            QCoreApplication.translate("InstalledPage", "Update"),
            update_icon(self.themed(UPDATE_COLOR)),
            self.update_selected,
        )
        self.remove_button = self._action_button(
            QCoreApplication.translate("InstalledPage", "Uninstall"),
            trash_icon(self.themed(UPDATE_COLOR)),
            self.remove_selected,
        )
        summary.addWidget(self.details_button)
        summary.addWidget(self.update_button)
        summary.addWidget(self.remove_button)
        footer = QHBoxLayout()
        footer.addWidget(self.footer)
        footer.addStretch(1)
        footer.addWidget(note)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 22)
        layout.setSpacing(14)
        layout.addLayout(filters)
        layout.addLayout(summary)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, 1)
        layout.addLayout(footer)

        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.table.itemChanged.connect(self._item_changed)
        self.origin.currentIndexChanged.connect(self._filter)
        self.search.textChanged.connect(self._filter)
        self.case_button.toggled.connect(self._filter)
        self.regex_button.toggled.connect(self._filter)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_SECONDS * 1000)
        self.timer.timeout.connect(lambda: self.load())
        # the app builds the page again when its menu is built again, and the old
        # one goes away: what listened for it stops with it
        stops = [
            ctx.events.on(CONTEXT_CHANGED, lambda **_: self.load()),
            ctx.events.on(WRITE_MODE_CHANGED, lambda **_: self._stamp_checks()),
            ctx.events.on(THEME_CHANGED, lambda **_: self.restyle()),
        ]
        self.destroyed.connect(lambda *_: [stop() for stop in stops])

    def _action_button(
        self, text: str, icon: QIcon, handler: Callable[[], None]
    ) -> QPushButton:
        """A button of the row of the summary, like the ones of the lists."""
        button = QPushButton(text)
        button.setIcon(icon)
        button.setProperty("variant", "secondary")
        button.clicked.connect(handler)
        return button

    def restyle(self) -> None:
        """The theme changed: the colors of the icons, the badges and the cells
        are the new ones."""
        self.details_button.setIcon(info_icon(self.themed(UPDATE_COLOR)))
        self.update_button.setIcon(update_icon(self.themed(UPDATE_COLOR)))
        self.remove_button.setIcon(trash_icon(self.themed(UPDATE_COLOR)))
        self.check_header.viewport().update()
        self._render()

    def themed(self, color: str) -> str:
        ui = self.ctx.ui
        return str(ui.themed(color)) if ui is not None else color

    # ----- loading

    def shown(self) -> None:
        """The page is opened: read it, and keep looking while it is shown."""
        self.load()
        self.timer.start()

    def hideEvent(self, event: Any) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def reload(self) -> None:
        """The refresh button of the header."""
        self.load(quiet=False)

    def load(self, quiet: bool = True) -> None:
        context = self.ctx.current_context
        ui = self.ctx.ui
        if not context or ui is None or self._loading:
            return
        self._loading = True
        ui.run_action(
            self._read,
            self._arrived,
            context,
            on_error=self._failed,
            quiet=quiet,
        )

    def _read(self, context: str) -> tuple[list[Any], dict[tuple[str, str, str], str]]:
        """The rows and the latest version of each, off the UI thread."""
        _namespaces, rows = self.ctx.cluster.get_resources(context, None, "Addon")
        cluster_version = ""
        if any(row.kind == "Addon" for row in rows):
            cluster_version = self._cluster_version(context)
        newest = latest.latest_versions(
            rows,
            lambda addon: latest.eks_latest(
                self.ctx.aws, context, addon, cluster_version
            ),
            lambda row: self.ctx.cluster.helm_chart_name(
                context, row.namespace, row.name
            ),
        )
        return rows, newest

    def _cluster_version(self, context: str) -> str:
        try:
            name = latest.cluster_name(self.ctx.cluster.eks_target(context))
            document = self.ctx.aws.run(
                context, ["eks", "describe-cluster", "--name", name]
            )
        except ClusterError as error:
            logger.info("The version of the cluster was not read: %s", error)
            return ""
        return str((document.get("cluster") or {}).get("version") or "")

    def _arrived(
        self, answer: tuple[list[Any], dict[tuple[str, str, str], str]]
    ) -> None:
        self._loading = False
        self.rows, self.newest = answer
        self.notice.setVisible(False)
        self._apply_sort()  # the order the person chose stays when it is read again
        self._render()

    def _failed(self, message: str) -> None:
        self._loading = False
        self.notice.setText(message)
        self.notice.setVisible(True)

    # ----- drawing

    def _installed(self, row: Any) -> str:
        """The version that is compared with the latest: the chart of a Helm
        release, the app of anything else."""
        return row.values[1] if row.kind == "HelmRelease" else row.values[2]

    def _newest(self, row: Any) -> str:
        return self.newest.get((row.kind, row.namespace, row.name), latest.NONE)

    def _cells(self, row: Any) -> tuple[str, ...]:
        """What the cells of a row say, in the order of the columns."""
        return (
            row.name,
            status_text(row.values[0]),
            row.values[1],
            row.values[2],
            self._newest(row),
            row.values[3],
            row.values[4],
            row.age,
        )

    def _sort_by(self, column: int) -> None:
        """A click on a header: sort by that column, and again to reverse."""
        if self._sort is not None and self._sort[0] == column:
            flipped = self._sort[1] == Qt.SortOrder.AscendingOrder
            order = (
                Qt.SortOrder.DescendingOrder if flipped else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        self._sort = (column, order)
        self.check_header.setSortIndicatorShown(True)
        self.check_header.setSortIndicator(column, order)
        self._apply_sort()
        self._render()

    def _apply_sort(self) -> None:
        if self._sort is None:
            return
        column, order = self._sort
        self.rows.sort(
            key=lambda row: (
                natural_key(self._cells(row)[column]),
                row.name.casefold(),
            ),
            reverse=order == Qt.SortOrder.DescendingOrder,
        )

    def _render(self) -> None:
        color = QColor(self.themed(TEXT_COLOR))
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            newest = self._newest(row)
            for column, text in enumerate(self._cells(row)):
                item = QTableWidgetItem(text)
                item.setForeground(color)
                if column == STATUS:
                    text_color, fill = badge_colors(row.values[0])
                    item.setData(
                        BADGE_ROLE, (self.themed(text_color), self.themed(fill))
                    )
                if column == LATEST and latest.update_available(
                    self._installed(row), newest
                ):  # a newer version is out: its icon, and the tip says which
                    item.setIcon(update_icon(self.themed(UPDATE_COLOR)))
                    item.setToolTip(
                        QCoreApplication.translate(
                            "InstalledPage", "Update available: {latest}"
                        ).format(latest=newest)
                    )
                self.table.setItem(index, column, item)
        self._filter()
        self._stamp_checks()

    # ----- the boxes (in the write mode, as the lists of the app have them)

    def _key(self, row: Any) -> tuple[str, str, str]:
        return (row.kind, row.namespace, row.name)

    def _checks_on(self) -> bool:
        return bool(self.ctx.app.write_mode)

    def _stamp_checks(self) -> None:
        """Put the boxes in the rows, or take them away when the write mode is
        off, and forget the rows that are gone."""
        on = self._checks_on()
        self._checked &= {self._key(row) for row in self.rows}
        if not on:
            self._checked.clear()
        self._filling = True
        try:
            for index, row in enumerate(self.rows):
                item = self.table.item(index, NAME)
                if item is None:
                    continue
                if on:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if self._key(row) in self._checked
                        else Qt.CheckState.Unchecked
                    )
                else:
                    item.setData(Qt.ItemDataRole.CheckStateRole, None)
        finally:
            self._filling = False
        self.check_header.set_column(NAME if on else -1)
        self._sync_checks()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        """The person checked or unchecked a box."""
        if (
            self._filling
            or item.column() != NAME
            or item.data(Qt.ItemDataRole.CheckStateRole) is None
            or not 0 <= item.row() < len(self.rows)
        ):
            return
        key = self._key(self.rows[item.row()])
        if item.checkState() == Qt.CheckState.Checked:
            self._checked.add(key)
        else:
            self._checked.discard(key)
        self._sync_checks()

    def _check_all(self, checked: bool) -> None:
        """The box of the header: check or uncheck every row that shows."""
        self._filling = True
        try:
            for index, row in enumerate(self.rows):
                if self.table.isRowHidden(index):
                    continue
                (self._checked.add if checked else self._checked.discard)(
                    self._key(row)
                )
                item = self.table.item(index, NAME)
                if item is not None:
                    item.setCheckState(
                        Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                    )
        finally:
            self._filling = False
        self._sync_checks()

    def _sync_checks(self) -> None:
        """The box of the header says whether none, some or all of the rows
        that show are checked, and the buttons follow."""
        shown = [
            row
            for index, row in enumerate(self.rows)
            if not self.table.isRowHidden(index)
        ]
        marked = sum(self._key(row) in self._checked for row in shown)
        if not self._checks_on() or not marked:
            state = Qt.CheckState.Unchecked
        elif marked == len(shown):
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.check_header.set_check_state(state)
        self._sync_buttons()

    def _targets(self) -> list[Any]:
        """The rows the buttons act on: the ones with the box checked, or else
        the one that is selected."""
        if self._checks_on() and self._checked:
            return [
                row
                for index, row in enumerate(self.rows)
                if self._key(row) in self._checked and not self.table.isRowHidden(index)
            ]
        selected = self.table.selectionModel().selectedRows()
        return [self.rows[one.row()] for one in selected if one.row() < len(self.rows)]

    def _sync_buttons(self) -> None:
        targets = self._targets()
        one = targets[0] if len(targets) == 1 else None
        many = len(targets) > 1
        # what works on one row only goes away when several are checked
        self.details_button.setVisible(not many)
        self.update_button.setVisible(not many)
        self.details_button.setEnabled(one is not None)
        self.update_button.setEnabled(
            one is not None and one.kind != GKE_KIND and self._checks_on()
        )
        self.remove_button.setVisible(self._checks_on())
        self.remove_button.setEnabled(
            bool(targets) and all(row.kind != GKE_KIND for row in targets)
        )

    def show_details(self) -> None:
        """The document of the row, as the cluster or the cloud tells it."""
        targets = self._targets()
        ui = self.ctx.ui
        context = self.ctx.current_context
        if len(targets) != 1 or ui is None or not context:
            return
        row = targets[0]
        ui.run_action(
            self.ctx.cluster.get_resource_details,
            lambda document: ui.show_json(f"{row.kind} {row.name}", document),
            context,
            row.kind,
            row.namespace,
            row.name,
            on_error=lambda message: ui.show_message(
                "warning", self.tr("Plugins"), message
            ),
        )

    def update_selected(self) -> None:
        targets = self._targets()
        if len(targets) == 1:
            self.update_row(targets[0])

    def _matches(self, index: int, pattern: Any) -> bool:
        return any(
            pattern.search(item.text())
            for column in range(self.table.columnCount())
            if (item := self.table.item(index, column)) is not None
        )

    def _filter(self, *_args: object) -> None:
        import re

        origin = self.origin.currentData()
        text = self.search.text()
        pattern = None
        self.search.setToolTip("")
        if text.strip():
            query = text if self.regex_button.isChecked() else re.escape(text.strip())
            try:
                pattern = re.compile(
                    query, 0 if self.case_button.isChecked() else re.IGNORECASE
                )
            except re.error as error:  # every row stays until it compiles
                self.search.setToolTip(str(error))
        shown = 0
        for index, row in enumerate(self.rows):
            matches = not origin or origin == origin_of(row.kind)
            if matches and pattern is not None:
                matches = self._matches(index, pattern)
            self.table.setRowHidden(index, not matches)
            shown += matches
        self.summary.setText(
            QCoreApplication.translate(
                "InstalledPage", "{visible} of {total} Add-ons"
            ).format(visible=shown, total=len(self.rows))
        )
        self.footer.setText(
            QCoreApplication.translate(
                "InstalledPage", "{count} Add-ons in the cluster"
            ).format(count=len(self.rows))
        )
        self._sync_checks()

    # ----- updating

    def _menu(self, position: QPoint) -> None:
        index = self.table.rowAt(position.y())
        if not 0 <= index < len(self.rows):
            return
        self.table.selectRow(index)
        row = self.rows[index]
        if row.kind == GKE_KIND:  # a GKE add-on is on or off
            return
        menu = QMenu(self)
        menu.addAction(self.tr("Update")).triggered.connect(
            lambda: self.update_row(row)
        )
        menu.addAction(self.tr("Uninstall")).triggered.connect(
            lambda: self.remove_rows([row])
        )
        menu.exec(self.table.viewport().mapToGlobal(position))

    def update_row(self, row: Any) -> None:
        """Ask for what the update takes, show the command and have the app run
        it, in the write mode only."""
        ui = self.ctx.ui
        context = self.ctx.current_context
        if ui is None or not context:
            return
        if not self.ctx.app.write_mode:
            ui.show_message(
                "information",
                self.tr("Plugins"),
                self.tr("Turn on the write mode to update a plugin."),
            )
            return
        steps: dict[str, tuple[Callable[..., Any], tuple[Any, ...]]] = {
            "Addon": (latest.eks_versions, (self.ctx.aws, context, row.name)),
            AKS_KIND: (self.ctx.cluster.aks_cluster, (context,)),
        }
        function, arguments = steps.get(
            row.kind,
            (
                latest.helm_match,
                (
                    self.ctx.cluster.helm_chart_name(context, row.namespace, row.name),
                    row.values[1],
                ),
            ),
        )
        ui.run_action(
            function,
            lambda found: self._dialog(row, context, found),
            *arguments,
            on_error=lambda message: self._dialog(row, context, None, message),
        )

    def _dialog(self, row: Any, context: str, found: Any, problem: str = "") -> None:
        ui = self.ctx.ui
        if ui is None:
            return
        if problem:
            ui.show_message("warning", self.tr("Plugins"), problem)
        versions: list[str] = []
        repository = ""
        target = ("", "")
        if row.kind == "Addon" and found:
            versions = list(found)
        elif row.kind == AKS_KIND and found:
            target = (found[0], found[1])
        elif row.kind == "HelmRelease" and found:
            repository, versions = found
        eks_target: list[str] = []
        if row.kind == "Addon":
            try:
                eks_target = self.ctx.cluster.eks_target(context)
            except ClusterError as error:
                ui.show_message("warning", self.tr("Plugins"), str(error))
                return
        newest = self.newest.get((row.kind, row.namespace, row.name), latest.NONE)
        dialog = PluginUpdateDialog(
            self,
            context,
            row,
            self._installed(row),
            newest,
            versions,
            repository,
            eks_target,
            target,
            self.ctx.cluster.helm_chart_name(context, row.namespace, row.name)
            if row.kind == "HelmRelease"
            else "",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.arguments:
            return
        ui.run_action(
            self.ctx.writes.run_update,
            lambda _output: self._updated(row),
            context,
            dialog.arguments,
            on_error=lambda message: ui.show_message(
                "warning", self.tr("Plugins"), message
            ),
        )

    def _updated(self, row: Any) -> None:
        self._notify(self.tr("Updated {name}").format(name=row.name))
        self.load()

    def _notify(self, message: str) -> None:
        """Tell that something was done with a notice of the system, which does
        not stand in the way; a desktop that cannot show one gets a message."""
        ui = self.ctx.ui
        if ui is None:
            return
        if not ui.show_system_notification(self.tr("Plugins"), message, None, "task"):
            ui.show_message("information", self.tr("Plugins"), message)

    # ----- uninstalling

    def remove_selected(self) -> None:
        """The button of the page: uninstall what the boxes or the selection
        name."""
        self.remove_rows(self._targets())

    def remove_rows(self, rows: list[Any]) -> None:
        """Uninstall add-ons and releases, one or many: show the commands, ask,
        and have the app run them one after the other, in the write mode."""
        ui = self.ctx.ui
        context = self.ctx.current_context
        rows = [row for row in rows if row.kind != GKE_KIND]
        if ui is None or not context or not rows:
            return
        if not self.ctx.app.write_mode:
            ui.show_message(
                "information",
                self.tr("Plugins"),
                self.tr("Turn on the write mode to uninstall a plugin."),
            )
            return
        ui.run_action(
            self._removal_commands,
            lambda commands: self._confirm_removal(context, commands),
            context,
            rows,
            on_error=lambda message: ui.show_message(
                "warning", self.tr("Plugins"), message
            ),
        )

    def _removal_commands(
        self, context: str, rows: list[Any]
    ) -> list[tuple[Any, list[str]]]:
        """The command that uninstalls each row, off the UI thread (an AKS
        cluster is looked up with the cloud's program)."""
        commands: list[tuple[Any, list[str]]] = []
        eks_target: list[str] = []
        aks: tuple[str, str] = ("", "")
        for row in rows:
            if row.kind == "Addon":
                eks_target = eks_target or self.ctx.cluster.eks_target(context)
                commands.append(
                    (row, updates.eks_delete_arguments(eks_target, row.name))
                )
            elif row.kind == AKS_KIND:
                aks = aks if aks[0] else self.ctx.cluster.aks_cluster(context)
                commands.append(
                    (row, updates.aks_delete_arguments(aks[0], aks[1], row.name))
                )
            else:
                commands.append(
                    (
                        row,
                        updates.helm_uninstall_arguments(
                            context, row.namespace, row.name
                        ),
                    )
                )
        return commands

    def _confirm_removal(
        self, context: str, commands: list[tuple[Any, list[str]]]
    ) -> None:
        ui = self.ctx.ui
        if ui is None:
            return
        missing = [one[1][0] for one in commands if updates.program_missing(one[1][0])]
        if missing:
            ui.show_message(
                "warning",
                self.tr("Plugins"),
                self.tr(
                    "{program} is not installed, so KubeScope cannot run this. "
                    "Install it, or copy the command and run it where it is."
                ).format(program=missing[0]),
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Uninstall"))
        box.setText(
            self.tr("Uninstall {count} from the cluster? This will run:").format(
                count=len(commands)
            )
        )
        box.setInformativeText(
            "\n".join(updates.commands(args) for _row, args in commands)
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        ui.style_box(box)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self._remove_next(context, list(commands), 0, [], len(commands))

    def _remove_next(
        self,
        context: str,
        pending: list[tuple[Any, list[str]]],
        done: int,
        failures: list[str],
        total: int,
    ) -> None:
        """Run the next command; a failure is kept and does not stop the
        others."""
        ui = self.ctx.ui
        if ui is None:
            return
        if not pending:
            self._removed(done, failures, total)
            return
        row, arguments = pending[0]
        rest = pending[1:]
        ui.run_action(
            self.ctx.writes.run_remove,
            lambda _output: self._remove_next(context, rest, done + 1, failures, total),
            context,
            arguments,
            on_error=lambda message: self._remove_next(
                context, rest, done, [*failures, f"{row.name}: {message}"], total
            ),
        )

    def _removed(self, done: int, failures: list[str], total: int) -> None:
        ui = self.ctx.ui
        if ui is None:
            return
        if done:
            self._notify(
                self.tr("Uninstalled {done} of {total}").format(done=done, total=total)
            )
        if failures:
            ui.show_message("warning", self.tr("Plugins"), "\n".join(failures))
        self.load()
