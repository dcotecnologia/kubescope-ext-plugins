from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem, QTableWidget, QTableWidgetItem

from kubescope.plugins.badge import BADGE_ROLE, BadgeDelegate


def draw(
    item: QTableWidgetItem,
) -> tuple[QTableWidget, BadgeDelegate, QModelIndex, QImage]:
    table = QTableWidget(1, 1)  # kept by the caller, or Qt deletes the delegate
    table.setItem(0, 0, item)
    delegate = BadgeDelegate(table)
    index = table.model().index(0, 0)
    image = QImage(200, 40, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 200, 40)
    option.font = table.font()
    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()
    return table, delegate, index, image


def test_a_cell_with_colors_is_drawn_as_a_pill_and_made_room_for() -> None:
    item = QTableWidgetItem("Synced")
    item.setData(BADGE_ROLE, ("#176b58", "#e5f4eb"))
    _table, delegate, index, image = draw(item)
    plain_table, plain_delegate, plain_index, plain_image = draw(
        QTableWidgetItem("Synced")
    )

    assert image.pixelColor(30, 20).name() != "#ffffff"  # the pill is not white
    assert plain_image.pixelColor(100, 5).name() == "#ffffff"
    option = QStyleOptionViewItem()
    assert (
        delegate.sizeHint(option, index).width()
        > plain_delegate.sizeHint(option, plain_index).width()
    )
    assert plain_table.rowCount() == 1
