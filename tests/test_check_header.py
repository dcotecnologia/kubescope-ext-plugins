from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTableWidget

from kubescope.plugins.check_header import CheckHeader

KEPT: list[QTableWidget] = []  # until the end: a table that goes first crashes Qt


def make() -> tuple[QTableWidget, CheckHeader]:
    table = QTableWidget(2, 2)
    KEPT.append(table)
    header = CheckHeader(table, lambda color: color)
    table.setHorizontalHeader(header)
    header.setSectionsClickable(True)
    table.setHorizontalHeaderLabels(["NAME", "STATUS"])
    table.resize(400, 200)
    table.show()
    return table, header


def test_the_box_is_drawn_in_the_column_in_each_of_its_states() -> None:
    _table, header = make()

    for state in (
        Qt.CheckState.Unchecked,
        Qt.CheckState.PartiallyChecked,
        Qt.CheckState.Checked,
    ):
        header.set_column(0)
        header.set_check_state(state)
        assert not header.grab().isNull()  # the section and the box are painted

    header.set_check_state(Qt.CheckState.Checked)  # the same state: nothing to draw
    header.set_column(0)
    header.set_column(-1)  # no box: the sections are the usual ones
    assert not header.grab().isNull()


def test_a_click_on_the_box_asks_for_every_row_and_one_elsewhere_sorts() -> None:
    _table, header = make()
    header.set_column(0)
    asked: list[bool] = []
    clicked: list[int] = []
    header.toggled.connect(asked.append)
    header.sectionClicked.connect(clicked.append)
    box = header._box().center()

    QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=box)
    header.set_check_state(Qt.CheckState.Checked)
    QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=box)
    elsewhere = QPoint(header.sectionViewportPosition(1) + 10, box.y())
    QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=elsewhere)

    assert asked == [True, False]  # check them all, then none
    assert clicked == [1]  # a click that is not on the box is a click to sort


def test_the_box_ignores_the_other_buttons_and_a_header_without_one() -> None:
    _table, header = make()
    asked: list[bool] = []
    header.toggled.connect(asked.append)
    box = header._box().center()

    QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=box)  # no box
    header.set_column(0)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        box,
        header.viewport().mapToGlobal(box),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    header.mousePressEvent(event)

    assert asked == []
