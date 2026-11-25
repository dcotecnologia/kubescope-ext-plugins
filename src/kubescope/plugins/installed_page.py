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

from kubescope.sdk import CONTEXT_CHANGED, THEME_CHANGED, WRITE_MODE_CHANGED, translate
from kubescope.sdk.errors import ClusterError
from kubescope.sdk.models import natural_key

from kubescope.plugins import latest, updates
from kubescope.plugins.update_dialog import AKS_KIND, PluginUpdateDialog

logger = logging.getLogger(__name__)

GKE_KIND = "GkeAddon"
POLL_SECONDS = 30  # how often the page looks again while it is shown
ROW_HEIGHT = 46  # as the rows of the lists of the app
FIELD_HEIGHT = 38
UPDATE_COLOR = "#3220a0"
NAME, STATUS, CHART, APP, LATEST, SOURCE, UPDATED, AGE = range(8)
WIDTHS = (258, 130, 130, 90, 100, 90, 100)  # as the lists of the app


def origin_of(kind: str) -> str:
    """`helm` for a Helm release, `cluster` for what the cloud lists."""
    return "helm" if kind == "HelmRelease" else "cluster"


def status_text(value: str) -> str:
    """A status as the clouds and Helm word it, in the interface language; a
    word that is not known stays as it came."""
    known = {
        "ACTIVE": translate("InstalledPage", "Active"),
        "CREATING": translate("InstalledPage", "Creating"),
        "UPDATING": translate("InstalledPage", "Updating"),
        "DELETING": translate("InstalledPage", "Deleting"),
        "DEGRADED": translate("InstalledPage", "Degraded"),
        "FAILED": translate("InstalledPage", "Failed"),
        "CREATE_FAILED": translate("InstalledPage", "Creation failed"),
        "UPDATE_FAILED": translate("InstalledPage", "Update failed"),
        "DELETE_FAILED": translate("InstalledPage", "Deletion failed"),
        "PENDING": translate("InstalledPage", "Pending"),
        "DEPLOYED": translate("InstalledPage", "Active"),
        "OUTDATED": translate("InstalledPage", "Outdated"),
        "SUPERSEDED": translate("InstalledPage", "Superseded"),
        "UNINSTALLED": translate("InstalledPage", "Uninstalled"),
        "UNINSTALLING": translate("InstalledPage", "Uninstalling"),
        "PENDING_INSTALL": translate("InstalledPage", "Pending install"),
        "PENDING_UPGRADE": translate("InstalledPage", "Pending upgrade"),
        "PENDING_ROLLBACK": translate("InstalledPage", "Pending rollback"),
    }
    key = value.strip().upper().replace(" ", "_").replace("-", "_")
    return known.get(key, value)


class InstalledPage:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.rows: list[Any] = []
        self._sort: tuple[int, bool] | None = None
        self._checked: set[tuple[str, str, str]] = set()
        self.newest: dict[tuple[str, str, str], str] = {}
        self._loading = False

        components = self.ctx.ui.components
        self.widget = components.widget(shown=self.shown, hidden=self.hidden)
        self.origin = components.filter_select(
            [
                (translate("InstalledPage", "All origins"), ""),
                ("Helm", "helm"),
                (translate("InstalledPage", "Cluster"), "cluster"),
            ]
        )
        self.search = components.search_box(
            translate("InstalledPage", "Search all columns...")
        )
        self.case_button = components.switch_button(
            "Aa", translate("InstalledPage", "Match case")
        )
        self.regex_button = components.switch_button(
            ".*", translate("InstalledPage", "Regular expression")
        )
        self.summary = components.label(variant="summary")
        self.table = components.data_table(
            [
                translate("InstalledPage", "NAME"),
                translate("InstalledPage", "STATUS"),
                translate("InstalledPage", "CHART"),
                translate("InstalledPage", "APP"),
                translate("InstalledPage", "LATEST"),
                translate("InstalledPage", "SOURCE"),
                translate("InstalledPage", "LAST UPDATE"),
                translate("InstalledPage", "AGE"),
            ],
            WIDTHS,
            checkable=True,
        )
        self.check_header = self.table.horizontalHeader()
        self.check_header.toggled.connect(self._check_all)
        self.sorter = components.header_sorter(self.table, self._ordered)
        self._filling = False
        components.on_context_menu(self.table, self._menu)
        self.footer = components.muted_label()
        note = components.muted_label(
            translate("InstalledPage", "Data fetched from the cluster API")
        )
        self.notice = components.label(variant="muted", wrap=True)

        filters = components.row(
            components.label(translate("InstalledPage", "ORIGIN"), "filter"),
            self.origin,
            self.search,
            self.case_button,
            self.regex_button,
            None,
        )
        self.details_button = self._action_button(
            translate("InstalledPage", "Details"),
            components.icon("info", self.themed(UPDATE_COLOR)),
            self.show_details,
        )
        self.update_button = self._action_button(
            translate("InstalledPage", "Update"),
            components.icon("update", self.themed(UPDATE_COLOR)),
            self.update_selected,
        )
        self.remove_button = self._action_button(
            translate("InstalledPage", "Uninstall"),
            components.icon("trash", self.themed(UPDATE_COLOR)),
            self.remove_selected,
        )
        components.page(
            self.widget,
            filters=filters,
            actions=components.row(
                self.summary,
                None,
                self.details_button,
                self.update_button,
                self.remove_button,
                spacing=6,
            ),
            notice=self.notice,
            body=self.table,
            footer=components.row(self.footer, None, note),
        )

        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.table.itemChanged.connect(self._item_changed)
        self.origin.currentIndexChanged.connect(self._filter)
        self.search.textChanged.connect(self._filter)
        self.case_button.toggled.connect(self._filter)
        self.regex_button.toggled.connect(self._filter)
        self.timer = components.timer(
            POLL_SECONDS * 1000, lambda: self.load(), self.widget
        )
        # the app builds the page again when its menu is built again, and the old
        # one goes away: what listened for it stops with it
        stops = [
            ctx.events.on(CONTEXT_CHANGED, lambda **_: self.load()),
            ctx.events.on(WRITE_MODE_CHANGED, lambda **_: self._stamp_checks()),
            ctx.events.on(THEME_CHANGED, lambda **_: self.restyle()),
        ]
        self.widget.destroyed.connect(lambda *_: [stop() for stop in stops])

    def _action_button(self, text: str, icon: Any, handler: Callable[[], None]) -> Any:
        """A button of the row of the summary, like the ones of the lists."""
        return self.ctx.ui.components.button(text, icon=icon, on_click=handler)

    def restyle(self) -> None:
        """The theme changed: the colors of the icons, the badges and the cells
        are the new ones."""
        self.details_button.setIcon(
            self.ctx.ui.components.icon("info", self.themed(UPDATE_COLOR))
        )
        self.update_button.setIcon(
            self.ctx.ui.components.icon("update", self.themed(UPDATE_COLOR))
        )
        self.remove_button.setIcon(
            self.ctx.ui.components.icon("trash", self.themed(UPDATE_COLOR))
        )
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

    def hidden(self) -> None:
        self.timer.stop()

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

    def _status(self, row: Any) -> str:
        """The status of a row: `Outdated` when a newer version is out."""
        if latest.update_available(self._installed(row), self._newest(row)):
            return "Outdated"
        return row.values[0]

    def _cells(self, row: Any) -> tuple[str, ...]:
        """What the cells of a row say, in the order of the columns."""
        return (
            row.name,
            status_text(self._status(row)),
            row.values[1],
            row.values[2],
            self._newest(row),
            row.values[3],
            row.values[4],
            row.age,
        )

    def _ordered(self, column: int, descending: bool) -> None:
        """A click on a header: the rows in that order."""
        self._sort = (column, descending)
        self._apply_sort()
        self._render()

    def _apply_sort(self) -> None:
        if self._sort is None:
            return
        column, descending = self._sort
        self.rows.sort(
            key=lambda row: (
                natural_key(self._cells(row)[column]),
                row.name.casefold(),
            ),
            reverse=descending,
        )

    def _render(self) -> None:
        components = self.ctx.ui.components
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            newest = self._newest(row)
            for column, text in enumerate(self._cells(row)):
                item = components.table_item(text, text)  # whole, when the cell cuts it
                if column == STATUS:
                    self.ctx.ui.components.set_badge(item, self._status(row))
                if column == SOURCE:  # the origin is a badge too, in a neutral tone
                    self.ctx.ui.components.set_badge(item, "")
                if column == LATEST and latest.update_available(
                    self._installed(row), newest
                ):  # a newer version is out: its icon, and the tip says which
                    item.setIcon(components.icon("update", self.themed(UPDATE_COLOR)))
                    item.setToolTip(
                        translate("InstalledPage", "Update available: {latest}").format(
                            latest=newest
                        )
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
        components = self.ctx.ui.components
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
                components.set_item_checked(
                    item, self._key(row) in self._checked if on else None
                )
        finally:
            self._filling = False
        self.check_header.set_column(NAME if on else -1)
        self._sync_checks()

    def _item_changed(self, item: Any) -> None:
        """The person checked or unchecked a box."""
        if (
            self._filling
            or item.column() != NAME
            or self.ctx.ui.components.item_checked(item) is None
            or not 0 <= item.row() < len(self.rows)
        ):
            return
        key = self._key(self.rows[item.row()])
        if self.ctx.ui.components.item_checked(item):
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
                    self.ctx.ui.components.set_item_checked(item, checked)
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
        state: bool | None
        if not self._checks_on() or not marked:
            state = False
        elif marked == len(shown):
            state = True
        else:
            state = None  # some of them
        self.check_header.set_checked(state)
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
        # what changes the cluster is out of sight while the app is read-only
        self.update_button.setVisible(not many and self._checks_on())
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
                "warning",
                translate("InstalledPage", "Plugins"),
                message,
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
            translate("InstalledPage", "{visible} of {total} Add-ons").format(
                visible=shown, total=len(self.rows)
            )
        )
        self.footer.setText(
            translate("InstalledPage", "{count} Add-ons in the cluster").format(
                count=len(self.rows)
            )
        )
        self._sync_checks()

    # ----- updating

    def _menu(self, x: int, y: int) -> None:
        index = self.table.rowAt(y)
        if not 0 <= index < len(self.rows):
            return
        self.table.selectRow(index)
        row = self.rows[index]
        if row.kind == GKE_KIND:  # a GKE add-on is on or off
            return
        menu = self.ctx.ui.components.menu(self.widget)
        if self._checks_on():  # what changes the cluster, in the write mode only
            menu.addAction(translate("InstalledPage", "Update")).triggered.connect(
                lambda: self.update_row(row)
            )
            menu.addAction(translate("InstalledPage", "Uninstall")).triggered.connect(
                lambda: self.remove_rows([row])
            )
        menu.addAction(translate("InstalledPage", "Details")).triggered.connect(
            self.show_details
        )
        self.ctx.ui.components.show_menu(menu, self.table, x, y)

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
                translate("InstalledPage", "Plugins"),
                translate(
                    "InstalledPage", "Turn on the write mode to update a plugin."
                ),
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
            ui.show_message(
                "warning",
                translate("InstalledPage", "Plugins"),
                problem,
            )
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
                ui.show_message(
                    "warning",
                    translate("InstalledPage", "Plugins"),
                    str(error),
                )
                return
        newest = self.newest.get((row.kind, row.namespace, row.name), latest.NONE)
        dialog = PluginUpdateDialog(
            self.widget,
            self.ctx.ui.components,
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
        if not dialog.exec() or not dialog.arguments:
            return
        ui.run_action(
            self.ctx.writes.run_update,
            lambda _output: self._updated(row),
            context,
            dialog.arguments,
            on_error=lambda message: ui.show_message(
                "warning",
                translate("InstalledPage", "Plugins"),
                message,
            ),
        )

    def _updated(self, row: Any) -> None:
        self._notify(translate("InstalledPage", "Updated {name}").format(name=row.name))
        self.load()

    def _notify(self, message: str) -> None:
        """Tell that something was done with a notice of the system, which does
        not stand in the way; a desktop that cannot show one gets a message."""
        ui = self.ctx.ui
        if ui is None:
            return
        if not ui.show_system_notification(
            translate("InstalledPage", "Plugins"),
            message,
            None,
            "task",
        ):
            ui.show_message(
                "information",
                translate("InstalledPage", "Plugins"),
                message,
            )

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
                translate("InstalledPage", "Plugins"),
                translate(
                    "InstalledPage", "Turn on the write mode to uninstall a plugin."
                ),
            )
            return
        ui.run_action(
            self._removal_commands,
            lambda commands: self._confirm_removal(context, commands),
            context,
            rows,
            on_error=lambda message: ui.show_message(
                "warning",
                translate("InstalledPage", "Plugins"),
                message,
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
                translate("InstalledPage", "Plugins"),
                translate(
                    "InstalledPage",
                    "{program} is not installed, so KubeScope cannot run this. "
                    "Install it, or copy the command and run it where it is.",
                ).format(program=missing[0]),
            )
            return
        if not self.ctx.ui.components.confirm(
            self.widget,
            translate("InstalledPage", "Uninstall"),
            translate(
                "InstalledPage", "Uninstall {count} from the cluster? This will run:"
            ).format(count=len(commands)),
            translate("InstalledPage", "Uninstall"),
            "\n".join(updates.commands(args) for _row, args in commands),
            warning=True,
        ):
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
                translate("InstalledPage", "Uninstalled {done} of {total}").format(
                    done=done, total=total
                )
            )
        if failures:
            ui.show_message(
                "warning",
                translate("InstalledPage", "Plugins"),
                "\n".join(failures),
            )
        self.load()
