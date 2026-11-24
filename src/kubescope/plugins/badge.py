"""A cell drawn as a badge, a rounded pill, like the status of the lists of the
app."""

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

BADGE_ROLE = Qt.ItemDataRole.UserRole + 5  # (text color, fill color)
PADDING = 8
BADGE_PADDING = 10
BADGE_HEIGHT = 20


class BadgeDelegate(QStyledItemDelegate):
    """Draws the text of a cell that carries the colors of a badge as a pill;
    any other cell is drawn as usual."""

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().initStyleOption(option, index)
        if index.data(BADGE_ROLE):
            option.text = ""  # the badge draws the text

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        colors = index.data(BADGE_ROLE)
        if not colors:
            return
        text_color, fill = (QColor(color) for color in colors)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        font = option.font
        font.setBold(True)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font)
        width = painter.fontMetrics().horizontalAdvance(text) + 2 * BADGE_PADDING
        rect = QRectF(
            option.rect.left() + PADDING,
            option.rect.top() + (option.rect.height() - BADGE_HEIGHT) / 2,
            min(width, option.rect.width() - PADDING),
            BADGE_HEIGHT,
        )
        border = QColor(text_color)
        border.setAlpha(90)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, BADGE_HEIGHT / 2, BADGE_HEIGHT / 2)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        hint = super().sizeHint(option, index)
        if not index.data(BADGE_ROLE):
            return hint
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        width = option.fontMetrics.horizontalAdvance(text)  # the badge draws it
        return QSize(width + 2 * BADGE_PADDING + 2 * PADDING, hint.height())
