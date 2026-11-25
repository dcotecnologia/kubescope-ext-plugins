from kubescope.sdk.errors import ClusterError
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QTableWidgetItem

from kubescope.plugins import installed_page, latest
from kubescope.plugins.installed_page import InstalledPage
from tests.conftest import resource


def build(ctx, monkeypatch):
    monkeypatch.setattr(latest, "helm_latest", lambda chart, installed: "2.0.0")
    ctx.aws.answers["describe-addon-versions"] = {
        "addons": [
            {
                "addonVersions": [
                    {
                        "addonVersion": "v9",
                        "compatibilities": [{"clusterVersion": "1.35"}],
                    }
                ]
            }
        ]
    }
    ctx.aws.answers["describe-cluster"] = {"cluster": {"version": "1.35"}}
    ctx.cluster.rows = [
        resource("Addon", "vpc-cni", "", ("ACTIVE", "—", "v1", "EKS", "3d")),
        resource("HelmRelease", "web"),
        resource("GkeAddon", "lb", "", ("Enabled", "—", "—", "GKE", "—")),
    ]
    ctx.cluster.charts["web"] = "site"
    page = InstalledPage(ctx)
    page.load()
    return page


def texts(page, column):
    return [page.table.item(r, column).text() for r in range(page.table.rowCount())]


def test_the_page_lists_the_rows_with_the_latest_version_of_each(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    assert texts(page, installed_page.NAME) == ["vpc-cni", "web", "lb"]
    assert texts(page, installed_page.LATEST) == ["v9", "2.0.0", "—"]
    first = page.table.item(0, installed_page.LATEST)
    plain = page.table.item(2, installed_page.LATEST)
    status = page.table.item(1, installed_page.STATUS)
    assert first is not None and plain is not None and status is not None
    assert not first.icon().isNull() and first.toolTip().endswith("v9")
    assert plain.icon().isNull()
    assert status.data(installed_page.BADGE_ROLE)
    assert ctx.cluster.asked == [("prod", None, "Addon")]
    assert page.summary.text() == "3 of 3 Add-ons"
    assert page.footer.text() == "3 Add-ons in the cluster"


def test_the_origin_and_the_search_hide_rows(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    page.origin.setCurrentIndex(page.origin.findData("helm"))
    assert [page.table.isRowHidden(r) for r in range(3)] == [True, False, True]
    page.origin.setCurrentIndex(page.origin.findData("cluster"))
    assert [page.table.isRowHidden(r) for r in range(3)] == [False, True, False]
    page.search.setText("vpc")
    assert [page.table.isRowHidden(r) for r in range(3)] == [False, True, True]
    assert page.summary.text() == "1 of 3 Add-ons"


def test_a_failure_is_said_and_a_busy_or_contextless_page_asks_nothing(
    ctx, monkeypatch
) -> None:
    ctx.cluster.failure = ClusterError("denied")
    page = InstalledPage(ctx)
    page.load()
    assert page.notice.text() == "denied" and not page._loading
    page._loading = True
    page.load()
    ctx.cluster.asked.clear()
    page._loading = False
    ctx.current_context = None
    page.load()
    ctx.ui = None
    ctx.current_context = "prod"
    page.load()
    assert ctx.cluster.asked == []


def test_the_page_is_read_when_it_is_shown(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    ctx.cluster.asked.clear()
    page.shown()
    assert len(ctx.cluster.asked) == 1


def test_the_version_of_a_cluster_that_cannot_be_read_is_left_empty(ctx) -> None:
    ctx.aws.failure = ClusterError("denied")
    ctx.cluster.rows = [
        resource("Addon", "vpc-cni", "", ("ACTIVE", "—", "v1", "EKS", "3d"))
    ]
    page = InstalledPage(ctx)
    page.load()
    assert texts(page, installed_page.LATEST) == ["—"]


class Accepting:
    """A dialog that is accepted at once with the command it was given."""

    arguments = ["helm", "upgrade"]
    seen: tuple = ()

    def __init__(self, *args) -> None:
        Accepting.seen = args

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


def test_an_update_needs_the_write_mode(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    ctx.app.write_mode = False
    page.update_row(page.rows[1])
    assert ctx.ui.messages[-1][0] == "information"
    assert ctx.writes.updates == []


def test_an_update_shows_the_dialog_and_has_the_app_run_the_command(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Accepting)
    monkeypatch.setattr(
        latest, "helm_match", lambda chart, installed: ("https://r", ["2.0.0"])
    )
    for row in page.rows[:2]:
        page.update_row(row)
    assert ctx.writes.updates == [("prod", ["helm", "upgrade"])] * 2
    assert ctx.ui.notices[-1] == ("Plugins", "Updated web")  # a notice, not a dialog
    assert Accepting.seen[5:7] == (["2.0.0"], "https://r")
    assert Accepting.seen[9] == "site"  # the chart of the release, not its name


def test_an_aks_extension_asks_for_its_cluster_and_an_eks_one_for_its_target(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Accepting)
    page.update_row(resource("AksExtension", "flux", "", ("ok", "—", "1", "AKS", "—")))
    assert Accepting.seen[7:9] == ([], ("aks-prod", "group"))
    page.update_row(page.rows[0])
    assert Accepting.seen[7][0] == "--cluster-name"


def test_a_refused_dialog_or_a_failed_update_runs_or_says_nothing_more(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)

    class Refusing(Accepting):
        def exec(self) -> QDialog.DialogCode:  # type: ignore[override]
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Refusing)
    page.update_row(page.rows[1])
    assert ctx.writes.updates == []
    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Accepting)
    ctx.writes.failure = ClusterError("helm failed")
    page.update_row(page.rows[1])
    assert ctx.ui.messages[-1] == ("warning", "Plugins", "helm failed")


def test_a_failure_reading_the_versions_is_said_and_the_dialog_still_opens(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Accepting)
    ctx.aws.failure = ClusterError("denied")
    page.update_row(page.rows[0])
    assert ("warning", "Plugins", "denied") in ctx.ui.messages
    assert Accepting.seen[5] == []


def test_an_eks_context_that_has_no_cluster_stops_the_update(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)

    def refuse(_context):
        raise ClusterError("not EKS")

    ctx.cluster.eks_target = refuse
    page._dialog(page.rows[0], "prod", ["v9"])
    assert ctx.ui.messages[-1][2] == "not EKS"


def test_without_a_window_or_a_context_an_update_does_nothing(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Accepting)
    ctx.current_context = None
    page.update_row(page.rows[1])
    window, ctx.ui = ctx.ui, None
    page._dialog(page.rows[1], "prod", None)
    page._updated(page.rows[1])
    ctx.ui = window
    assert ctx.writes.updates == []


class FakeAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.run = lambda: None
        self.triggered = self

    def connect(self, function) -> None:
        self.run = function


class FakeMenu:
    """A menu that is not shown: it keeps what it was given."""

    shown: list = []

    def __init__(self, _parent) -> None:
        self.actions: list = []

    def addAction(self, text):
        action = FakeAction(text)
        self.actions.append(action)
        return action

    def exec(self, _position) -> None:
        FakeMenu.shown.append(self)


def test_the_menu_offers_update_but_not_for_a_gke_add_on(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    FakeMenu.shown = []
    monkeypatch.setattr(installed_page, "QMenu", FakeMenu)
    monkeypatch.setattr(installed_page.PluginUpdateDialog, "exec", lambda self: 0)
    for y in (60, 110, 5000):  # a Helm release, a GKE add-on, outside the rows
        page._menu(QPoint(5, y))
    assert len(FakeMenu.shown) == 1
    action = FakeMenu.shown[0].actions[0]
    assert action.text == "Update"
    action.run()  # opens the dialog, which is not shown


def test_the_search_switches_match_the_case_and_read_a_regular_expression(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)

    def hidden():
        return [page.table.isRowHidden(r) for r in range(3)]

    page.search.setText("VPC")
    assert hidden() == [False, True, True]
    page.case_button.setChecked(True)
    assert hidden() == [True, True, True]
    page.case_button.setChecked(False)
    page.regex_button.setChecked(True)
    page.search.setText("^(vpc|web)")
    assert hidden() == [False, False, True]
    page.search.setText("(")  # does not compile: every row stays
    assert hidden() == [False, False, False] and page.search.toolTip()


def test_the_statuses_are_badges_in_the_colors_of_the_app() -> None:
    assert installed_page.badge_colors("deployed")[0] == "#176b58"
    assert installed_page.badge_colors("UPDATE_FAILED")[0] == "#a33d45"
    assert installed_page.badge_colors("pending-upgrade")[0] == "#985415"
    assert installed_page.badge_colors("whatever")[0] == "#505963"
    assert installed_page.status_text("deployed") == "Active"
    assert installed_page.status_text("Odd") == "Odd"


def test_the_page_is_read_again_while_it_is_shown_and_not_when_hidden(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    page.shown()
    assert page.timer.isActive()
    page.show()
    page.hide()
    assert not page.timer.isActive()
    ctx.cluster.asked.clear()
    page.reload()
    assert ctx.ui.quiet[-1] is False and len(ctx.cluster.asked) == 1
    ctx.events.fire("context_changed", context="dev")
    assert len(ctx.cluster.asked) == 2


def test_the_icons_and_the_cells_are_drawn_again_when_the_theme_changes(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    ctx.ui.themed = lambda color, text=False: "#ff0000"
    ctx.events.fire("theme_changed")
    status = page.table.item(0, installed_page.STATUS)
    assert status is not None
    assert status.data(installed_page.BADGE_ROLE) == ("#ff0000", "#ff0000")
    assert not page.update_button.icon().isNull()


def test_a_click_on_a_header_sorts_the_rows_and_a_second_one_reverses_them(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    assert texts(page, installed_page.NAME) == ["vpc-cni", "web", "lb"]

    page._sort_by(installed_page.NAME)
    assert texts(page, installed_page.NAME) == ["lb", "vpc-cni", "web"]
    assert page.check_header.sortIndicatorSection() == installed_page.NAME

    page._sort_by(installed_page.NAME)
    assert texts(page, installed_page.NAME) == ["web", "vpc-cni", "lb"]

    page._sort_by(installed_page.AGE)  # the same age: by name
    assert texts(page, installed_page.NAME) == ["lb", "vpc-cni", "web"]

    page._sort_by(installed_page.NAME)
    page.load()  # read again: the order the person chose stays
    assert texts(page, installed_page.NAME) == ["lb", "vpc-cni", "web"]


def checked(page, *names) -> None:
    for index, row in enumerate(page.rows):
        item = page.table.item(index, installed_page.NAME)
        assert item is not None
        item.setCheckState(
            Qt.CheckState.Checked if row.name in names else Qt.CheckState.Unchecked
        )


def test_the_boxes_come_with_the_write_mode_and_go_with_it(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    first = page.table.item(0, installed_page.NAME)
    assert first is not None and first.checkState() == Qt.CheckState.Unchecked
    assert page.check_header.column == installed_page.NAME

    checked(page, "web")
    assert page._checked == {("HelmRelease", "ops", "web")}

    ctx.app.write_mode = False
    ctx.events.fire("write_mode_changed", write_mode=False)

    assert page._checked == set() and page.check_header.column == -1
    assert first.data(Qt.ItemDataRole.CheckStateRole) is None

    page.rows.append(
        resource("Addon", "extra", "")
    )  # a row the table does not have yet
    ctx.app.write_mode = True
    page._stamp_checks()
    assert page.check_header.column == installed_page.NAME


def test_a_box_of_a_row_that_is_gone_or_not_a_box_is_ignored(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    plain = page.table.item(0, installed_page.CHART)
    assert plain is not None
    page._item_changed(plain)  # not the column of the boxes
    box = page.table.item(0, installed_page.NAME)
    assert box is not None
    page._filling = True
    page._item_changed(box)  # the page is setting it, not the person
    page._filling = False
    gone = QTableWidgetItem("x")
    page.table.setRowCount(4)
    page.table.setItem(3, installed_page.NAME, gone)
    gone.setCheckState(Qt.CheckState.Checked)  # a row beyond the list
    assert page._checked == set()


def test_the_box_of_the_header_checks_and_unchecks_the_rows_that_show(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    page.table.setRowHidden(2, True)  # a row the search hides is left alone

    page.check_header.toggled.emit(True)
    assert len(page._checked) == 2
    assert page.check_header.check_state == Qt.CheckState.Checked

    page.table.takeItem(0, installed_page.NAME)  # a row with no cell
    page.check_header.toggled.emit(False)
    assert page._checked == set()
    assert page.check_header.check_state == Qt.CheckState.Unchecked

    page.check_header.toggled.emit(True)
    page.table.setRowHidden(2, False)
    page._sync_checks()
    assert page.check_header.check_state == Qt.CheckState.PartiallyChecked


def test_the_buttons_act_on_the_rows_with_a_box_or_else_on_the_selected_one(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    assert not page.details_button.isEnabled()  # nothing is selected

    page.table.selectRow(1)
    assert page.details_button.isEnabled() and page.update_button.isEnabled()
    page.table.selectRow(2)  # a GKE add-on is on or off: nothing to update to
    assert page.details_button.isEnabled() and not page.update_button.isEnabled()

    checked(page, "web", "vpc-cni")  # two boxes: no one row to act on
    assert not page.details_button.isEnabled()
    checked(page, "web")
    assert page.details_button.isEnabled()
    assert [row.name for row in page._targets()] == ["web"]


def test_details_asks_the_cluster_for_the_document_of_the_row(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    page.show_details()  # no row yet
    assert ctx.ui.documents == []

    checked(page, "web")
    page.show_details()
    assert ctx.ui.documents == [
        ("HelmRelease web", {"kind": "HelmRelease", "name": "web"})
    ]

    ctx.cluster.failure = ClusterError("denied")
    page.show_details()
    assert ctx.ui.messages[-1] == ("warning", "Plugins", "denied")

    ctx.current_context = None
    ctx.cluster.asked.clear()
    page.show_details()
    assert ctx.cluster.asked == []


def test_the_update_button_updates_the_one_row_it_acts_on(ctx, monkeypatch) -> None:
    page = build(ctx, monkeypatch)
    monkeypatch.setattr(installed_page, "PluginUpdateDialog", Accepting)
    monkeypatch.setattr(latest, "helm_match", lambda chart, installed: ("", ["2.0.0"]))

    page.update_selected()  # nothing to act on
    assert ctx.writes.updates == []

    checked(page, "web")
    page.update_selected()
    assert ctx.writes.updates == [("prod", ["helm", "upgrade"])]


class Answer:
    """The confirmation of an uninstall, answered at once."""

    yes = True
    shown: list = []

    def __init__(self, parent) -> None:
        self.parts: dict = {}

    def setIcon(self, _icon) -> None:
        pass

    def setWindowTitle(self, title) -> None:
        self.parts["title"] = title

    def setText(self, text) -> None:
        self.parts["text"] = text

    def setInformativeText(self, text) -> None:
        self.parts["commands"] = text

    def setStandardButtons(self, _buttons) -> None:
        pass

    def setDefaultButton(self, _button) -> None:
        pass

    def exec(self):
        Answer.shown.append(self.parts)
        return (
            QMessageBox.StandardButton.Yes
            if Answer.yes
            else QMessageBox.StandardButton.No
        )


def uninstall(page, monkeypatch, yes=True, missing=False):
    Answer.yes, Answer.shown = yes, []
    monkeypatch.setattr(
        installed_page,
        "QMessageBox",
        type(
            "Box",
            (Answer,),
            {"Icon": QMessageBox.Icon, "StandardButton": QMessageBox.StandardButton},
        ),
    )
    monkeypatch.setattr(installed_page.updates, "program_missing", lambda _p: missing)


def test_releases_and_add_ons_are_uninstalled_after_the_commands_are_shown(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    uninstall(page, monkeypatch)
    aks = resource("AksExtension", "flux", "", ("ok", "—", "1", "AKS", "—"))
    page.rows.append(aks)

    page.remove_rows(
        [page.rows[0], page.rows[1], aks, page.rows[2]]
    )  # the GKE one is left

    [shown] = Answer.shown
    assert "Uninstall 3" in shown["text"]
    assert shown["commands"].splitlines()[0].startswith("aws eks delete-addon")
    assert [args[:3] for _c, args in ctx.writes.removals] == [
        ["aws", "eks", "delete-addon"],
        ["helm", "--kube-context", "prod"],
        ["az", "k8s-extension", "delete"],
    ]
    assert ctx.ui.notices[-1] == ("Plugins", "Uninstalled 3 of 3")


def test_declining_uninstalls_nothing_and_it_needs_the_write_mode(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    uninstall(page, monkeypatch, yes=False)

    page.remove_rows([page.rows[1]])
    assert ctx.writes.removals == []

    ctx.app.write_mode = False
    page.remove_rows([page.rows[1]])
    assert ctx.ui.messages[-1][0] == "information"

    ctx.app.write_mode = True
    page.remove_rows([page.rows[2]])  # a GKE add-on is on or off
    page.remove_rows([])
    ctx.current_context = None
    page.remove_rows([page.rows[1]])
    assert Answer.shown and len(Answer.shown) == 1


def test_a_missing_program_a_failed_lookup_and_a_failed_command_are_said(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    uninstall(page, monkeypatch, missing=True)
    page.remove_rows([page.rows[1]])
    assert "is not installed" in ctx.ui.messages[-1][2] and Answer.shown == []

    uninstall(page, monkeypatch)
    ctx.cluster.eks_target = lambda _context: (_ for _ in ()).throw(
        ClusterError("not EKS")
    )
    page.remove_rows([page.rows[0]])
    assert ctx.ui.messages[-1] == ("warning", "Plugins", "not EKS")

    ctx.writes.removal_failures["web"] = ClusterError("busy")
    page.remove_rows([page.rows[1], page.rows[1]])  # one fails, the next is still run
    assert ctx.ui.messages[-1] == ("warning", "Plugins", "web: busy\nweb: busy")
    assert ctx.ui.notices == []  # nothing was uninstalled to tell about


def test_the_menu_uninstalls_and_a_page_without_a_window_does_nothing(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    uninstall(page, monkeypatch)
    FakeMenu.shown = []
    monkeypatch.setattr(installed_page, "QMenu", FakeMenu)
    page._menu(QPoint(5, 60))
    FakeMenu.shown[0].actions[1].run()
    assert FakeMenu.shown[0].actions[1].text == "Uninstall"
    assert ctx.writes.removals

    window, ctx.ui = ctx.ui, None
    page._confirm_removal("prod", [])
    page._remove_next("prod", [], 0, [], 0)
    page._removed(1, [], 1)
    page._notify("x")
    ctx.ui = window
    page._removed(0, [], 1)  # nothing was done: nothing to tell


def test_a_system_that_cannot_notify_gets_a_message_and_the_buttons_follow_the_boxes(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    ctx.ui.can_notify = False
    page._notify("Updated web")
    assert ctx.ui.messages[-1] == ("information", "Plugins", "Updated web")

    page.show()
    assert not page.remove_button.isHidden() and not page.remove_button.isEnabled()
    page.table.selectRow(1)
    assert page.remove_button.isEnabled()
    checked(page, "web", "vpc-cni")  # several: what works on one row goes away
    assert page.details_button.isHidden() and page.update_button.isHidden()
    assert page.remove_button.isEnabled()
    checked(page, "web", "lb")  # a GKE add-on cannot be uninstalled
    assert not page.remove_button.isEnabled()
    checked(page)
    assert not page.details_button.isHidden() and not page.update_button.isHidden()
    ctx.app.write_mode = False
    ctx.events.fire("write_mode_changed", write_mode=False)
    assert page.remove_button.isHidden()


def test_the_bin_icon_is_drawn() -> None:
    assert not installed_page.trash_icon("#3220a0").isNull()


def test_the_button_uninstalls_the_rows_with_a_box_or_the_selected_one(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    uninstall(page, monkeypatch)
    page.show()

    checked(page, "web")
    page.remove_button.click()

    assert [args[3] for _c, args in ctx.writes.removals] == ["uninstall"]


def test_what_changes_the_cluster_is_out_of_sight_while_the_app_is_read_only(
    ctx, monkeypatch
) -> None:
    page = build(ctx, monkeypatch)
    ctx.app.write_mode = False
    ctx.events.fire("write_mode_changed", write_mode=False)
    page.table.selectRow(0)
    page._sync_buttons()
    assert page.update_button.isHidden() and page.remove_button.isHidden()
    assert not page.details_button.isHidden()  # looking is always allowed

    FakeMenu.shown = []
    monkeypatch.setattr(installed_page, "QMenu", FakeMenu)
    page._menu(QPoint(5, 60))
    assert [a.text for a in FakeMenu.shown[0].actions] == ["Details"]

    ctx.app.write_mode = True
    ctx.events.fire("write_mode_changed", write_mode=True)
    page.table.selectRow(0)
    page._sync_buttons()
    assert not page.update_button.isHidden() and not page.remove_button.isHidden()
    FakeMenu.shown = []
    page._menu(QPoint(5, 60))
    assert [a.text for a in FakeMenu.shown[0].actions] == [
        "Update",
        "Uninstall",
        "Details",
    ]
