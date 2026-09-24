"""MetaWipe Qt interface, retaining the visual components from version 2.3."""
from __future__ import annotations
from pathlib import Path
from typing import Callable
from .engine import (VERSION, MAX_FILE, KEEP, REMOVE, PROVENANCE, MetadataError,
                     Report, CleanResult, scan_image, human_size)
from .cleaner import clean_image
from .classification import classify, privacy_counts, privacy_summary
from .diff import metadata_diff
from .files import unique_output, discover, Cancelled
from .batch import process_batch, BatchItem, batch_summary
from .profiles import CleaningPolicy, PROFILE_LABELS, GROUP_LABELS, RECOMMENDED
from .reports import render_report, export_report
from .history import HistoryStore

def create_window(settings=None):
    """Qt presentation layer; engines, reports and jobs remain independent."""
    from string import Template
    from PySide6.QtCore import (
        Qt, QThread, Signal, QUrl, QSize, QRectF, QPointF, QSettings,
        QTimer, QVariantAnimation, QEasingCurve, QEvent,
    )
    from PySide6.QtGui import (
        QColor, QDesktopServices, QIcon, QImageReader, QKeySequence,
        QPainter, QPainterPath, QPalette, QPen, QPixmap, QShortcut, QFont,
        QFontDatabase, QFontMetrics,
    )
    from PySide6.QtWidgets import (
        QApplication, QAbstractItemView, QFileDialog, QFrame, QHBoxLayout,
        QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
        QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
        QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QBoxLayout,
        QGridLayout, QStyledItemDelegate, QStyle, QCheckBox, QComboBox, QMenu, QGraphicsOpacityEffect,
    )

    application = QApplication.instance()
    application.setStyle("Fusion")
    families = QFontDatabase.families()
    font_family = next((name for name in ("Inter", "Segoe UI", "Noto Sans", "DejaVu Sans")
                        if name in families), application.font().family())
    QImageReader.setAllocationLimit(128)

    # Shared tokens for QSS and custom Qt painting.
    themes = {
        "dark": dict(bg="#0D0F12", secondary="#121519", card="#171A1F",
                     elevated="#1C2026", input="#111419", border="#252A2F",
                     border_hover="#35393E", text="#F4F4F5", secondary_text="#A1A1AA",
                     muted="#71717A", accent="#8B9A6D", accent_hover="#9CAA7F",
                     on_accent="#11150D", success="#4ADE80", warning="#FBBF24",
                     danger="#F87171", selection="#2B3228", scrollbar="#363B43",
                     success_bg="#14251E", warning_bg="#282318", danger_bg="#2B1B20",
                     success_border="#254334", warning_border="#4A3D22", danger_border="#4E2C32",
                     logo_bg="#263540", logo_fg="#C1CDD5", logo_border="#344550"),
        "light": dict(bg="#F5F6F7", secondary="#EEF0F2", card="#FFFFFF",
                      elevated="#F0F2F4", input="#F8F9FA", border="#E3E6E9",
                      border_hover="#CDD2D8", text="#20242B", secondary_text="#5F6671",
                      muted="#777F89", accent="#66774F", accent_hover="#576641",
                      on_accent="#FFFFFF", success="#26824A", warning="#997021",
                      danger="#BC4450", selection="#E7EBDD", scrollbar="#C7CDD3",
                      success_bg="#F0F8F2", warning_bg="#FCF7EB", danger_bg="#FCF0F1",
                      success_border="#D8EADD", warning_border="#EDDFC1", danger_border="#EFD4D9",
                      logo_bg="#263540", logo_fg="#D8E1E7", logo_border="#344550"),
    }
    theme_state = {"dark": True}

    def token(name: str) -> str:
        return themes["dark" if theme_state["dark"] else "light"][name]

    def theme_color(color: str) -> str:
        if color in themes["dark"]:
            return token(color)
        # Keep existing panel icons compatible with both themes.
        if color.lower() == "#ffffff":
            return token("on_accent")
        return token("text" if QColor(color).lightness() < 95 else "secondary_text")

    def make_stylesheet() -> str:
        c = themes["dark" if theme_state["dark"] else "light"]
        return Template("""
            QWidget { color: $text; font-family: '$font'; font-size: 14px; }
            QMainWindow, QWidget#Shell, QWidget#Page { background: $bg; }
            QLabel { background: transparent; border: none; }
            QLabel#Title { font-size: 20px; font-weight: 600; }
            QLabel#Brand { font-size: 17px; font-weight: 600; }
            QLabel#Section { font-size: 14px; font-weight: 600; }
            QLabel#ResultTitle { font-size: 19px; font-weight: 600; }
            QLabel#Subtitle { color: $secondary_text; font-size: 14px; }
            QLabel#Muted { color: $secondary_text; font-size: 13px; }
            QLabel#Small { color: $secondary_text; font-size: 12px; }
            QLabel#Eyebrow { color: $muted; font-size: 11px; font-weight: 500; letter-spacing: 1px; }
            QLabel#Metric { font-size: 30px; font-weight: 600; }
            QLabel#Tag, QLabel#Keycap { color: $secondary_text; font-size: 11px;
                padding: 4px 7px; background: $elevated; border: 1px solid $border; border-radius: 6px; }
            QLabel#DropIcon { background: $elevated; border: 1px solid $border; border-radius: 14px; }
            QLabel#Logo { background: $logo_bg; border: 1px solid $logo_border; border-radius: 10px; }
            QLabel#FileTitle { font-size: 13px; font-weight: 600; }
            QFrame#Sidebar { background: $secondary; border-right: 1px solid $border; }
            QFrame#NavigationPanel { background: $bg; border: 1px solid $border; border-radius: 16px; }
            QScrollArea#NavigationScroll, QWidget#NavigationViewport, QWidget#NavigationContent {
                background: transparent; border: none; }
            QLabel#NavigationHeading { color: $muted; font-size: 10px; font-weight: 500;
                letter-spacing: 1px; padding: 5px 9px 2px 9px; }
            QFrame#Toolbar { background: $bg; border-bottom: 1px solid $border; }
            QFrame#Footer { background: $bg; border-top: 1px solid $border; }
            QFrame#Card { background: $card; border: 1px solid $border; border-radius: 14px; }
            QFrame#Line { background: $border; border: none; min-height: 1px; max-height: 1px; }
            QFrame#VerticalLine { background: $border; border: none; min-width: 1px; max-width: 1px; }
            QFrame#Drop { background: $input; border: 1px dashed $border_hover; border-radius: 10px; }
            QFrame#Drop[hover="true"] { background: $elevated; border-color: $accent; }
            QFrame#Drop[loaded="true"] { background: $input; border: 1px solid $border; }
            QFrame#Drop[hover="true"][loaded="true"] { border-color: $accent; background: $elevated; }
            QPushButton { background: $card; border: 1px solid $border; border-radius: 10px;
                padding: 10px 14px; font-size: 13px; font-weight: 500; }
            QPushButton:hover { background: $elevated; border-color: $border_hover; }
            QPushButton:focus { border-color: $accent; }
            QPushButton:disabled { color: $muted; background: $elevated; }
            QPushButton#Primary { padding: 12px 14px; font-weight: 600; }
            QPushButton#Nav { padding: 11px 12px; text-align: left; }
            QPushButton#Quiet { padding: 6px 5px; font-size: 12px; }
            QPushButton#IconButton { padding: 7px; }
            QPushButton#Filter { padding: 6px 12px; font-size: 12px; }
            QComboBox { background: $input; border: 1px solid $border; border-radius: 10px;
                padding: 10px 14px; min-height: 20px; }
            QComboBox:focus { border-color: $accent; }
            QComboBox::drop-down { border: none; width: 28px; }
            QComboBox QAbstractItemView { background: $card; selection-background-color: $selection; }
            QCheckBox { spacing: 8px; font-size: 13px; padding: 3px 0; }
            QCheckBox::indicator { width: 15px; height: 15px; }
            QMenu { background: $card; border: 1px solid $border_hover; padding: 6px; }
            QMenu::item { padding: 9px 24px; border-radius: 6px; }
            QMenu::item:selected { background: $elevated; }
            QTreeWidget::item { padding: 8px 4px; }
            QTreeWidget::item:selected { background: $selection; }
            QTreeWidget::item:hover { background: $elevated; }
            QLineEdit, QPlainTextEdit { background: $input; color: $text; border: 1px solid $border;
                border-radius: 10px; padding: 10px; selection-background-color: $selection; }
            QLineEdit:focus, QPlainTextEdit:focus { border-color: $accent; }
            QLineEdit#SearchInput { background: transparent; border: none; padding: 0; font-size: 13px; }
            QPlainTextEdit { font-size: 13px; }
            QTreeWidget { background: $card; border: none; outline: none; }
            QHeaderView { background: $bg; }
            QHeaderView::section { background: $bg; color: $muted; border: none;
                border-bottom: 1px solid $border; padding: 12px; font-size: 11px;
                font-weight: 500; letter-spacing: 0.7px; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 7px; margin: 2px 0; }
            QScrollBar:horizontal { background: transparent; height: 7px; margin: 0 2px; }
            QScrollBar::handle { background: $scrollbar; border-radius: 3px; min-height: 28px; min-width: 28px; }
            QScrollBar::handle:hover { background: $muted; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
            QProgressBar { background: $elevated; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: $accent; border-radius: 2px; }
            QToolTip { color: $text; background: $elevated; border: 1px solid $border_hover;
                border-radius: 7px; padding: 8px 10px; font-size: 12px; }
            QFrame#Status { border-radius: 10px; }
            QFrame#Status[tone="success"] { background: $success_bg; border: 1px solid $success_border; }
            QFrame#Status[tone="warning"] { background: $warning_bg; border: 1px solid $warning_border; }
            QFrame#Status[tone="danger"] { background: $danger_bg; border: 1px solid $danger_border; }
        """).substitute(c, font=font_family)

    def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
        widget = QLabel(text)
        widget.setTextFormat(Qt.TextFormat.PlainText)
        widget.setWordWrap(wrap)
        widget.setMinimumWidth(0)
        if name:
            widget.setObjectName(name)
        return widget

    def line(vertical: bool = False) -> QFrame:
        widget = QFrame()
        widget.setObjectName("VerticalLine" if vertical else "Line")
        return widget


    def symbol(name: str, size: int = 20, color: str = "secondary_text", exact: bool = False) -> QPixmap:
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 24, size / 24)
        painter.setPen(QPen(QColor(color if exact else theme_color(color)), 1.55, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        def stroke(*points):
            path = QPainterPath(QPointF(*points[0]))
            for point in points[1:]:
                path.lineTo(QPointF(*point))
            painter.drawPath(path)
        if name in {"image", "brand"}:
            painter.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2, 2)
            painter.drawEllipse(QPointF(16, 9), 1.6, 1.6)
            stroke((4, 17), (9, 12), (14, 17), (17, 14), (20, 17))
        elif name == "upload":
            stroke((4, 15), (4, 20), (20, 20), (20, 15))
            stroke((8, 8), (12, 4), (16, 8))
            stroke((12, 4), (12, 15))
        elif name == "scan":
            for points in (((4, 9), (4, 4), (9, 4)), ((15, 4), (20, 4), (20, 9)),
                           ((4, 15), (4, 20), (9, 20)), ((15, 20), (20, 20), (20, 15))):
                stroke(*points)
            stroke((8, 12), (16, 12))
        elif name == "clean":
            stroke((5, 14), (14, 5), (21, 12), (12, 21), (8, 21), (3, 16), (5, 14))
            stroke((7, 12), (14, 19))
            stroke((15, 21), (21, 21))
        elif name == "check":
            stroke((5, 12), (10, 17), (19, 7))
        elif name == "shield":
            path = QPainterPath(QPointF(12, 3))
            path.lineTo(20, 6)
            path.lineTo(20, 11)
            path.cubicTo(20, 16, 16, 19, 12, 21)
            path.cubicTo(8, 19, 4, 16, 4, 11)
            path.lineTo(4, 6)
            path.closeSubpath()
            painter.drawPath(path)
            stroke((8, 12), (11, 15), (16, 9))
        elif name == "folder":
            stroke((3, 19), (3, 6), (10, 6), (12, 9), (21, 9), (21, 19), (3, 19))
        elif name == "copy":
            painter.drawRoundedRect(QRectF(8, 8, 12, 13), 2, 2)
            stroke((15, 5), (15, 3), (4, 3), (4, 16), (5, 16))
        elif name == "search":
            painter.drawEllipse(QPointF(10.5, 10.5), 6, 6)
            stroke((15, 15), (20, 20))
        elif name == "close":
            stroke((6, 6), (18, 18))
            stroke((6, 18), (18, 6))
        elif name == "arrow":
            stroke((4, 12), (20, 12))
            stroke((15, 7), (20, 12), (15, 17))
        elif name == "tag":
            stroke((3, 4), (12, 4), (21, 13), (13, 21), (3, 11), (3, 4))
            painter.drawEllipse(QPointF(7.5, 8), 1.2, 1.2)
        elif name == "cpu":
            painter.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
            painter.drawRect(QRectF(9, 9, 6, 6))
            for position in (9, 15):
                stroke((position, 3), (position, 6))
                stroke((position, 18), (position, 21))
                stroke((3, position), (6, position))
                stroke((18, position), (21, position))
        elif name == "sliders":
            for x, y in ((5, 8), (12, 16), (19, 10)):
                stroke((x, 3), (x, y - 2))
                stroke((x, y + 2), (x, 21))
                painter.drawEllipse(QPointF(x, y), 2, 2)
        elif name == "sun":
            painter.drawEllipse(QPointF(12, 12), 4, 4)
            for points in (((12, 2), (12, 4)), ((12, 20), (12, 22)),
                           ((2, 12), (4, 12)), ((20, 12), (22, 12)),
                           ((5, 5), (6.5, 6.5)), ((17.5, 17.5), (19, 19)),
                           ((5, 19), (6.5, 17.5)), ((17.5, 6.5), (19, 5))):
                stroke(*points)
        elif name == "moon":
            path = QPainterPath(QPointF(18, 17))
            path.cubicTo(8, 21, 2, 10, 9, 4)
            path.cubicTo(5, 15, 16, 20, 21, 13)
            path.cubicTo(21, 15, 20, 16, 18, 17)
            painter.drawPath(path)
        elif name == "info":
            painter.drawEllipse(QPointF(12, 12), 9, 9)
            stroke((12, 11), (12, 16))
            painter.drawPoint(QPointF(12, 7.5))
        painter.end()
        return pixmap

    def icon(name: str, color: str = "#727269", size: int = 18) -> QIcon:
        return QIcon(symbol(name, size, color))

    def icon_label(name: str, size: int = 18, color: str = "#727269") -> QLabel:
        widget = label("")
        widget.setFixedSize(size, size)
        widget.setPixmap(symbol(name, size, color))
        widget.setProperty("theme_symbol", (name, size, color))
        return widget

    def button(text: str, name: str = "", glyph: str = "") -> QPushButton:
        widget = AnimatedButton(text)
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        if name:
            widget.setObjectName(name)
        if glyph:
            widget.setProperty("theme_symbol", (glyph, 18, "#ffffff" if name == "Primary" else "#75756c"))
            widget.setIcon(icon(glyph, "#ffffff" if name == "Primary" else "#75756c"))
            widget.setIconSize(QSize(16, 16))
        return widget

    def elide(widget: QLabel, text: str):
        widget.setToolTip(text)
        widget.setText(widget.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle,
                                                       max(80, widget.width())))

    def mix(a: str, b: str, progress: float) -> QColor:
        left, right = QColor(a), QColor(b)
        return QColor.fromRgbF(*(left.getRgbF()[i] * (1 - progress) + right.getRgbF()[i] * progress
                                 for i in range(4)))

    class Tween(QVariantAnimation):
        """Shared brief transitions that do not block the event loop."""
        def __init__(self, parent, value, callback):
            super().__init__(parent)
            self.value = value
            self.callback = callback
            self.setDuration(180)
            self.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.valueChanged.connect(self.changed)

        def changed(self, value):
            self.value = value
            self.callback(value)

        def to(self, value, animate=True):
            self.stop()
            if animate and self.value != value:
                self.setStartValue(self.value)
                self.setEndValue(value)
                self.start()
            else:
                self.changed(value)

    class AnimatedButton(QPushButton):
        def __init__(self, text=""):
            super().__init__(text)
            self.hover = Tween(self, 0.0, lambda _: self.update())
            self.feedback = Tween(self, 0.0, lambda _: self.update())
            self.setMinimumHeight(38)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        def sizeHint(self):
            font = self.font()
            font.setPixelSize(12 if self.objectName() in ("Quiet", "Filter") else 13)
            font.setWeight(QFont.Weight.DemiBold)
            width = QFontMetrics(font).horizontalAdvance(self.text().strip()) + 28
            if self.property("theme_symbol"):
                width += 16 + (8 if self.text().strip() else 0)
            hint = super().sizeHint()
            return QSize(max(hint.width(), width), max(38, hint.height()))

        def enterEvent(self, event):
            self.hover.to(1.0)
            super().enterEvent(event)

        def leaveEvent(self, event):
            self.hover.to(0.0)
            super().leaveEvent(event)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            kind = self.objectName()
            enabled = self.isEnabled()
            hover = float(self.hover.value) if enabled else 0
            background = mix(token("card"), token("elevated"), hover)
            border = mix(token("border"), token("border_hover"), hover)
            foreground = token("text")
            if kind == "Primary":
                background = mix(token("accent"), token("accent_hover"), hover)
                border = background
                foreground = token("on_accent")
            elif kind in ("Nav", "Quiet", "IconButton", "Filter"):
                background = QColor(token("elevated"))
                background.setAlphaF(1 if kind == "Nav" and self.isChecked() else hover * .7)
                border = QColor("transparent")
                foreground = token("text" if self.isChecked() or hover > .5 else "secondary_text")
                if kind == "Filter":
                    background.setAlpha(0)
            if self.isDown() and enabled and kind != "Filter":
                background = QColor(token("border_hover" if kind != "Primary" else "accent"))
            if not enabled:
                background, border = QColor(token("elevated")), QColor(token("border"))
                foreground = token("muted")
            if self.feedback.value:
                background = mix(background.name(), token("success_bg"), self.feedback.value)
                border = mix(border.name(), token("success_border"), self.feedback.value)
                foreground = token("success")
            if self.hasFocus() and enabled:
                border = QColor(token("accent"))
            painter.setPen(QPen(border, 1))
            painter.setBrush(background)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 10, 10)
            font = self.font()
            font.setPixelSize(12 if kind in ("Quiet", "Filter") else 13)
            font.setWeight(QFont.Weight.DemiBold if kind == "Primary" or self.isChecked() else QFont.Weight.Medium)
            painter.setFont(font)
            fm = painter.fontMetrics()
            spec = self.property("theme_symbol")
            icon_width = 16 if spec else 0
            gap = 8 if spec and self.text().strip() else 0
            text = fm.elidedText(self.text().strip(), Qt.TextElideMode.ElideRight,
                                 max(0, self.width() - 24 - icon_width - gap))
            content_width = fm.horizontalAdvance(text) + icon_width + gap
            x = 13 if kind == "Nav" and text else (self.width() - content_width) / 2
            if spec:
                painter.drawPixmap(round(x), (self.height() - 16) // 2,
                                   symbol(spec[0], 16, foreground, exact=True))
                x += icon_width + gap
            painter.setPen(QColor(foreground))
            painter.drawText(QRectF(x, 0, max(0, self.width() - x - 8), self.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    class CopyButton(AnimatedButton):
        def __init__(self, report):
            super().__init__("Copy report")
            self.report = report
            self.setProperty("theme_symbol", ("copy", 16, "secondary_text"))
            self.setIcon(icon("copy"))
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAccessibleName("Copy full report as JSON")
            self.setToolTip("Copy the full report as JSON")
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.timer.timeout.connect(self.restore)
            self.setFixedWidth(150)
            self.setText("Report  ▾")
            self.clicked.connect(self.open_menu)

        def open_menu(self):
            menu = QMenu(self)
            menu.addAction("Copy report", self.copy_report)
            menu.addSeparator()
            for extension in ("txt", "json", "csv"):
                menu.addAction("Export " + extension.upper(), lambda checked=False, fmt=extension: self.export(fmt))
            menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

        def export(self, format):
            path, _ = QFileDialog.getSaveFileName(self, "Export report", f"report.{format}", f"{format.upper()} (*.{format})",
                                                  options=QFileDialog.Option.DontConfirmOverwrite)
            if not path:
                return
            try:
                export_report(self.report, path, format)
                self.setText("Exported")
                self.feedback.to(1.0)
                self.timer.start(1500)
            except Exception as exc:
                QMessageBox.warning(self, "Report", "Could not export. Choose an unused filename.\n" + str(exc))

        def copy_report(self):
            QApplication.clipboard().setText(render_report(self.report))
            self.setText("Copied")
            self.setAccessibleName("Report copied")
            self.setProperty("theme_symbol", ("check", 16, "success"))
            self.feedback.to(1.0)
            self.timer.start(1500)

        def restore(self):
            self.setText("Report  ▾")
            self.setAccessibleName("Copy full report as JSON")
            self.setProperty("theme_symbol", ("copy", 16, "secondary_text"))
            self.feedback.to(0.0)

    class MetricCard(QFrame):
        def __init__(self, glyph, number, description, hint):
            super().__init__()
            self.hover = Tween(self, 0.0, lambda _: self.update())
            self.setMinimumWidth(0)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.setToolTip(hint)
            self.setAccessibleName(f"{number} {description}")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(18, 16, 18, 16)
            layout.setSpacing(4)
            layout.addWidget(icon_label(glyph, 17, "secondary_text"))
            layout.addSpacing(3)
            layout.addWidget(label(str(number), "Metric"))
            layout.addWidget(label(description, "Muted", True))

        def enterEvent(self, event):
            self.hover.to(1.0)
            super().enterEvent(event)

        def leaveEvent(self, event):
            self.hover.to(0.0)
            super().leaveEvent(event)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(mix(token("border"), token("border_hover"), self.hover.value), 1))
            painter.setBrush(mix(token("card"), token("elevated"), self.hover.value))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 14, 14)

    class MetricGrid(QWidget):
        def __init__(self, report):
            super().__init__()
            self.grid = QGridLayout(self)
            self.grid.setContentsMargins(0, 0, 0, 0)
            self.grid.setSpacing(12)
            self.cards = [
                MetricCard("tag", report.removable, "Removable metadata", "Items available for removal from the new copy."),
                MetricCard("cpu", report.ai_hints, "AI references", "Textual references recognized by Scan; they do not prove the origin of the image."),
                MetricCard("sliders", report.technical, "Technical data", "Recognized technical fields. The selected profile determines how removable fields are handled."),
            ]
            self.columns = 0
            self.reflow(3)

        def reflow(self, columns):
            if self.columns == columns:
                return
            self.columns = columns
            for card in self.cards:
                self.grid.removeWidget(card)
            for col in range(3):
                self.grid.setColumnStretch(col, 1 if col < columns else 0)
            for index, card in enumerate(self.cards):
                self.grid.addWidget(card, index // columns, index % columns)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.reflow(3 if self.width() >= 560 else 1)

    class SearchField(QWidget):
        def __init__(self):
            super().__init__()
            self.focus = Tween(self, 0.0, lambda _: self.update())
            self.setMinimumWidth(190)
            self.setFixedHeight(44)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row = QHBoxLayout(self)
            row.setContentsMargins(13, 0, 12, 0)
            row.setSpacing(10)
            row.addWidget(icon_label("search", 17))
            self.edit = QLineEdit()
            self.edit.setObjectName("SearchInput")
            self.edit.setPlaceholderText("Search metadata…")
            self.edit.setClearButtonEnabled(True)
            self.edit.setAccessibleName("Search metadata")
            self.edit.installEventFilter(self)
            row.addWidget(self.edit, 1)
            self.keycap = label("Ctrl K", "Keycap")
            self.keycap.setFixedHeight(24)
            self.keycap.setToolTip("Focus search · Ctrl+K")
            row.addWidget(self.keycap, 0, Qt.AlignmentFlag.AlignVCenter)
            self.setFocusProxy(self.edit)

        def eventFilter(self, watched, event):
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.focus.to(1.0 if event.type() == QEvent.Type.FocusIn else 0.0)
            return super().eventFilter(watched, event)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.keycap.setVisible(self.width() >= 295)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(token("input")))
            painter.setPen(QPen(mix(token("border"), token("accent"), self.focus.value), 1))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 10, 10)
            ring = QColor(token("accent"))
            ring.setAlphaF(.16 * self.focus.value)
            painter.setPen(QPen(ring, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 11, 11)

    class SegmentedControl(QWidget):
        changed = Signal(str)

        def __init__(self):
            super().__init__()
            self.setFixedHeight(44)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.row = QHBoxLayout(self)
            self.row.setContentsMargins(4, 4, 4, 4)
            self.row.setSpacing(2)
            self.buttons = []
            self.selected = 0
            self.slide = Tween(self, QRectF(), lambda _: self.update())
            for name in ("All", "Removable", "Technical"):
                item = button(name, "Filter")
                item.setMinimumHeight(0)
                item.setFixedHeight(36)
                item.setCheckable(True)
                item.setChecked(name == "All")
                item.clicked.connect(lambda checked=False, value=name: self.changed.emit(value))
                self.buttons.append(item)
                self.row.addWidget(item)

        def select(self, value, animate=True):
            for index, item in enumerate(self.buttons):
                item.setChecked(item.text() == value)
                if item.isChecked():
                    self.selected = index
            rect = QRectF(self.buttons[self.selected].geometry())
            self.slide.to(rect, animate and not self.slide.value.isEmpty())

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.row.activate()
            self.select(self.buttons[self.selected].text(), False)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(token("border")), 1))
            painter.setBrush(QColor(token("input")))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 11, 11)
            rect = self.slide.value
            if not rect.isEmpty():
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 25))
                painter.drawRoundedRect(rect.translated(0, 1.5), 8, 8)
                painter.setPen(QPen(QColor(token("border_hover")), .6))
                painter.setBrush(QColor(token("elevated")))
                painter.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), 8, 8)

    class ResponsiveRow(QWidget):
        def __init__(self, left, right, threshold=650):
            super().__init__()
            self.threshold = threshold
            self.row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
            self.row.setContentsMargins(0, 0, 0, 0)
            self.row.setSpacing(12)
            self.row.addWidget(left, 1)
            self.row.addWidget(right)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            narrow = self.width() < self.threshold
            self.row.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
            self.row.setAlignment(self.row.itemAt(1).widget(), Qt.AlignmentFlag.AlignLeft if narrow else Qt.AlignmentFlag.AlignVCenter)

    def entry_tooltip(entry):
        description = classify(entry).description
        if entry.ai_hint:
            description += "\nTextual AI reference; not a conclusion about the pixels."
        return description

    class MetadataDelegate(QStyledItemDelegate):
        def sizeHint(self, option, index):
            return QSize(super().sizeHint(option, index).width(), 48)

        def paint(self, painter, option, index):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            hover = self.parent().hover_values.get(index.row(), 0.0)
            background = QColor(token("selection")) if selected else mix(token("card"), token("elevated"), hover)
            painter.fillRect(option.rect, background)
            separator = QColor(token("border"))
            separator.setAlpha(140)
            painter.setPen(QPen(separator, 1))
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
            rect = QRectF(option.rect).adjusted(12, 0, -12, -1)
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            font = QFont(option.font)
            font.setPixelSize(13)
            font.setWeight(QFont.Weight.Medium if index.column() == 0 else QFont.Weight.Normal)
            painter.setFont(font)
            if index.column() in (2, 3):
                font.setPixelSize(11)
                font.setWeight(QFont.Weight.Medium)
                painter.setFont(font)
                fm = painter.fontMetrics()
                text = fm.elidedText(text, Qt.TextElideMode.ElideRight, max(0, int(rect.width() - 16)))
                badge = QRectF(rect.x(), rect.center().y() - 12, min(rect.width(), fm.horizontalAdvance(text) + 16), 24)
                removable = index.column() == 3 and index.data() == REMOVE
                painter.setPen(QPen(QColor(token("warning_border" if removable else "border_hover")), .6))
                painter.setBrush(QColor(token("warning_bg" if removable else "elevated")))
                painter.drawRoundedRect(badge, 6, 6)
                painter.setPen(QColor(token("warning" if removable else "secondary_text")))
                painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
            else:
                entry = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
                if index.column() == 0 and entry and entry.ai_hint:
                    painter.drawPixmap(int(rect.x()), int(rect.center().y() - 7), symbol("cpu", 14, "warning"))
                    rect.adjust(22, 0, 0, 0)
                painter.setPen(QColor(token("text" if index.column() == 0 else "secondary_text")))
                text = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(0, int(rect.width())))
                painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            if selected and index.column() == 0:
                painter.fillRect(option.rect.x(), option.rect.y() + 12, 2, 24, QColor(token("accent")))
            painter.restore()

    class MetadataTree(QTreeWidget):
        def __init__(self):
            super().__init__()
            self.hover_row = -1
            self.hover_values = {}
            self.hover_tweens = {}
            self.setMouseTracking(True)
            self.setItemDelegate(MetadataDelegate(self))
            self.setHeaderLabels(["FIELD", "CONTENT", "SOURCE", "ACTION"])
            self.setRootIsDecorated(False)
            self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.setUniformRowHeights(True)
            self.setTextElideMode(Qt.TextElideMode.ElideRight)
            self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            self.header().setMinimumSectionSize(66)
            self.header().setFixedHeight(40)
            for column in (0, 2, 3):
                self.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.header().setStretchLastSection(False)
            self.setAccessibleName("Analyzed metadata. Select a row to view the full content.")

        def hover_changed(self, row):
            if row == self.hover_row:
                return
            previous, self.hover_row = self.hover_row, row
            for index, target in ((previous, 0.0), (row, 1.0)):
                if index < 0:
                    continue
                if index not in self.hover_tweens:
                    def repaint(value, item=index):
                        self.hover_values[item] = value
                        self.viewport().update()
                    tween = Tween(self, 0.0, repaint)
                    self.hover_tweens[index] = tween
                    def forget(item=index):
                        if item != self.hover_row:
                            self.hover_values.pop(item, None)
                            self.hover_tweens.pop(item).deleteLater()
                    tween.finished.connect(forget)
                self.hover_tweens[index].to(target)

        def mouseMoveEvent(self, event):
            self.hover_changed(self.indexAt(event.position().toPoint()).row())
            super().mouseMoveEvent(event)

        def leaveEvent(self, event):
            self.hover_changed(-1)
            super().leaveEvent(event)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            available = self.viewport().width()
            self.setColumnWidth(0, min(200, max(110, int(available * .26))))
            self.setColumnWidth(2, 122 if available > 660 else 96)
            self.setColumnWidth(3, 136 if self.headerItem().text(3) == "STATUS" else 110 if available > 660 else 100)

    def status_card(report):
        tone = "danger" if report.blockers else "warning" if report.ai_hints or report.warnings or privacy_counts(report)["potentially_sensitive_count"] or privacy_counts(report)["sensitive_count"] else "success"
        frame = QFrame()
        frame.setObjectName("Status")
        frame.setProperty("tone", tone)
        row = QHBoxLayout(frame)
        row.setContentsMargins(15, 13, 16, 13)
        row.setSpacing(11)
        row.addWidget(icon_label("check" if tone == "success" else "info", 18, tone), 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(5)
        counts = privacy_counts(report)
        relevant = counts["sensitive_count"] + counts["potentially_sensitive_count"]
        heading = privacy_summary(report) if relevant else "No potentially sensitive metadata found"
        if report.removable == 0 and not report.blockers:
            heading = "Clean image · no removable metadata detected"
        words.addWidget(label(heading, "FileTitle", True))
        notes = [f"{report.ai_hints} textual AI references. They do not prove the origin of the image." if report.ai_hints else
                 "No known AI references in the analyzed metadata."]
        if any(entry.category == PROVENANCE for entry in report.entries):
            notes.append("Provenance data has not been authenticated.")
        if report.blockers:
            notes.append("Cleaning blocked: " + " ".join(dict.fromkeys(report.blockers)))
        if report.warnings:
            notes.append(" ".join(dict.fromkeys(report.warnings)))
        if notes:
            words.addWidget(label("\n".join(notes), "Small", True))
        row.addLayout(words, 1)
        return frame

    def empty_state():
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 30, 24, 30)
        layout.setSpacing(10)
        layout.addStretch()
        layout.addWidget(icon_label("search", 26, "muted"), alignment=Qt.AlignmentFlag.AlignHCenter)
        title = label("No metadata found", "Section", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = label("Try changing the search or filters.", "Muted", True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addStretch()
        return frame, subtitle


    class Job(QThread):
        result = Signal(object)
        failed = Signal(str)
        progress = Signal(str)

        def __init__(self, function: Callable, parent):
            super().__init__(parent)
            self.function = function

        def run(self):
            try:
                self.result.emit(self.function())
            except Exception as exc:
                self.failed.emit(str(exc) or type(exc).__name__)

    class ContentStack(QStackedWidget):
        """Fit the visible panel without reserving space for hidden panels."""

        def sizeHint(self):
            current = self.currentWidget()
            if current is None:
                return super().sizeHint()
            return current.sizeHint().expandedTo(current.minimumSize()).boundedTo(current.maximumSize())

        def minimumSizeHint(self):
            current = self.currentWidget()
            if current is None:
                return super().minimumSizeHint()
            return current.minimumSizeHint().expandedTo(current.minimumSize())

        def setCurrentIndex(self, index):
            super().setCurrentIndex(index)
            self.updateGeometry()

    class Preview(QWidget):
        def __init__(self):
            super().__init__()
            self.pixmap = None
            self.setMinimumWidth(100)
            self.setFixedHeight(190)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setToolTip("Preview scaled to fit the screen. The saved file is not resized.")

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if self.pixmap is None:
                painter.drawPixmap((self.width() - 36) // 2, (self.height() - 36) // 2,
                                   symbol("image", 36, "#99998e"))
                return
            scaled = self.pixmap.scaled(max(1, self.width() - 8), max(1, self.height() - 8),
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
            x, y = (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2
            if self.pixmap.hasAlphaChannel():
                for xx in range(x, x + scaled.width(), 10):
                    for yy in range(y, y + scaled.height(), 10):
                        color = "#eeeeE8" if ((xx - x) // 10 + (yy - y) // 10) % 2 else "#ffffff"
                        painter.fillRect(xx, yy, min(10, x + scaled.width() - xx),
                                         min(10, y + scaled.height() - yy), QColor(color))
            painter.drawPixmap(x, y, scaled)

    class DropZone(QFrame):
        selected = Signal(str)
        cleared = Signal()
        invalid = Signal(str)

        def __init__(self):
            super().__init__()
            self.setObjectName("Drop")
            self.setProperty("hover", False)
            self.setProperty("loaded", False)
            self.setAcceptDrops(True)
            self.setMinimumWidth(260)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.path = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(18, 18, 18, 16)
            self.stack = ContentStack()
            layout.addWidget(self.stack)

            empty = QWidget()
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(0, 10, 0, 8)
            empty_layout.setSpacing(12)
            empty_layout.addStretch()
            tile = label("", "DropIcon")
            tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile.setFixedSize(56, 56)
            tile.setPixmap(symbol("upload", 26, "#5a5a52"))
            tile.setProperty("theme_symbol", ("upload", 26, "#5a5a52"))
            empty_layout.addWidget(tile, alignment=Qt.AlignmentFlag.AlignHCenter)
            title = label("Drag an image here", "Section", True)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(title)
            hint = label("or choose a file from your computer", "Muted", True)
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(hint)
            self.choose = button("Select image", glyph="folder")
            self.choose.setToolTip("Select image · Ctrl+O")
            self.choose.clicked.connect(self.browse)
            empty_layout.addWidget(self.choose, alignment=Qt.AlignmentFlag.AlignHCenter)
            formats = label("PNG, JPEG & WebP  ·  Up to 256 MiB", "Small")
            formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(formats)
            empty_layout.addStretch()
            self.stack.addWidget(empty)

            loaded = QWidget()
            loaded_layout = QVBoxLayout(loaded)
            loaded_layout.setContentsMargins(0, 0, 0, 0)
            loaded_layout.setSpacing(14)
            self.preview = Preview()
            loaded_layout.addWidget(self.preview)
            loaded_layout.addWidget(line())
            file_row = QHBoxLayout()
            file_row.setSpacing(10)
            file_row.addWidget(icon_label("image", 20))
            file_text = QVBoxLayout()
            file_text.setSpacing(3)
            self.file_name = label("", "FileTitle")
            self.file_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.file_description = label("", "Small")
            file_text.addWidget(self.file_name)
            file_text.addWidget(self.file_description)
            file_row.addLayout(file_text, 1)
            self.change = button("", "IconButton", "folder")
            self.change.setFixedSize(30, 30)
            self.change.setToolTip("Choose another image")
            self.change.setAccessibleName("Choose another image")
            self.change.clicked.connect(self.browse)
            self.remove = button("", "IconButton", "close")
            self.remove.setFixedSize(30, 30)
            self.remove.setToolTip("Clear selection")
            self.remove.setAccessibleName("Clear selection")
            self.remove.clicked.connect(self.cleared.emit)
            file_row.addWidget(self.change)
            file_row.addWidget(self.remove)
            loaded_layout.addLayout(file_row)
            self.stack.addWidget(loaded)

        def browse(self):
            if not self.isEnabled():
                return
            initial = str(self.path.parent) if self.path else ""
            path, _ = QFileDialog.getOpenFileName(self, "Select image", initial,
                "Images (*.png *.apng *.jpg *.jpeg *.jpe *.webp);;All files (*)")
            if path:
                self.selected.emit(path)

        def restyle(self):
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

        def dragEnterEvent(self, event):
            urls = event.mimeData().urls()
            if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile():
                self.setProperty("hover", True)
                self.restyle()
                event.acceptProposedAction()
            else:
                event.ignore()

        def dragMoveEvent(self, event):
            if self.isEnabled() and event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dragLeaveEvent(self, event):
            self.setProperty("hover", False)
            self.restyle()
            event.accept()

        def dropEvent(self, event):
            self.setProperty("hover", False)
            self.restyle()
            if not self.isEnabled():
                event.ignore()
                return
            urls = event.mimeData().urls()
            if len(urls) != 1 or not urls[0].isLocalFile():
                self.invalid.emit("Drop one local image at a time.")
                return
            path = urls[0].toLocalFile()
            if not Path(path).is_file():
                self.invalid.emit("Select an image file instead of a folder.")
                return
            event.acceptProposedAction()
            self.selected.emit(path)

        def set_path(self, path: Path) -> tuple[str, str]:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            dimensions = reader.size()
            format_name = bytes(reader.format()).decode("ascii", errors="replace").upper()
            if dimensions.isValid():
                reader.setScaledSize(dimensions.scaled(QSize(900, 500), Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            self.preview.pixmap = None if image.isNull() else QPixmap.fromImage(image)
            self.preview.update()
            self.preview.setFixedHeight(190)
            self.file_description.setText(human_size(path.stat().st_size) + "  ·  Original file")
            self.path = path
            self.stack.setCurrentIndex(1)
            self.setProperty("loaded", True)
            self.restyle()
            elide(self.file_name, path.name)
            dimension_text = f"{dimensions.width()} × {dimensions.height()} px" if dimensions.isValid() else "—"
            return format_name or path.suffix.lstrip(".").upper(), dimension_text

        def reset(self):
            self.path = None
            self.preview.pixmap = None
            self.preview.setFixedHeight(190)
            self.stack.setCurrentIndex(0)
            self.setProperty("loaded", False)
            self.restyle()

        def compact(self):
            self.preview.setFixedHeight(90)
            self.stack.updateGeometry()
            self.updateGeometry()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self.path:
                elide(self.file_name, self.path.name)

    class ProfileControls(QFrame):
        """Select fields for one image or categories for a batch."""
        def __init__(self, window, batch=False):
            super().__init__()
            self.window, self.batch = window, batch
            self.report = None
            self.updating = False
            self.setObjectName("Card")
            box = QVBoxLayout(self)
            box.setContentsMargins(18, 18, 18, 18)
            box.setSpacing(12)
            box.addWidget(label("Cleaning profile", "Section"))
            self.combo = QComboBox()
            for key, title in PROFILE_LABELS.items():
                self.combo.addItem(title, key)
            self.combo.setCurrentIndex(max(0, self.combo.findData(window.settings.value("clean/profile", "privacy"))))
            box.addWidget(self.combo)
            self.description = label("", "Small", True)
            box.addWidget(self.description)
            self.custom = QWidget()
            custom_layout = QVBoxLayout(self.custom)
            custom_layout.setContentsMargins(0, 0, 0, 0)
            custom_layout.setSpacing(12)
            controls = QGridLayout()
            for index, (title, mode) in enumerate((("Select recommended", "recommended"), ("Select all", "all"), ("Clear selection", "none"))):
                item = button(title, "Quiet")
                item.clicked.connect(lambda checked=False, m=mode: self.select(m))
                controls.addWidget(item, index // 2, index % 2)
            custom_layout.addLayout(controls)
            self.groups = {}
            grid = QGridLayout()
            self.groups_grid = grid
            self.group_columns = 2
            for index, (key, title) in enumerate(GROUP_LABELS.items()):
                check = QCheckBox(title)
                check.setChecked(key in RECOMMENDED)
                check.toggled.connect(lambda checked, group=key: self.group_changed(group, checked))
                grid.addWidget(check, index // 2, index % 2)
                self.groups[key] = check
            custom_layout.addLayout(grid)
            self.tree = QTreeWidget()
            self.tree.setHeaderLabels(["FIELD", "SOURCE"])
            self.tree.setRootIsDecorated(False)
            self.tree.setMinimumHeight(160)
            self.tree.setMaximumHeight(260)
            self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.tree.itemChanged.connect(self.update_plan)
            self.tree.setVisible(not batch)
            custom_layout.addWidget(self.tree)
            custom_layout.addWidget(label("Resolution, orientation and color profiles required for display are protected. "
                "XMP, IPTC and provenance data are removed as whole blocks; removing signatures invalidates embedded provenance.", "Small", True))
            box.addWidget(self.custom)
            self.plan_label = label("", "Small", True)
            box.addWidget(self.plan_label)
            self.combo.currentIndexChanged.connect(self.changed)
            self.changed()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if not hasattr(self, "groups_grid"):
                return
            columns = 1 if self.width() < 720 else 2
            if columns != self.group_columns:
                self.group_columns = columns
                for index, widget in enumerate(self.groups.values()):
                    self.groups_grid.removeWidget(widget)
                    self.groups_grid.addWidget(widget, index // columns, index % columns)

        def changed(self):
            profile = self.combo.currentData()
            self.custom.setVisible(profile == "custom")
            descriptions = {
                "privacy": "Removes personal fields and potentially sensitive blocks. Keeps recognized technical information.",
                "full": "Removes all removable fields. Keeps the data required for correct display.",
                "technical": "Keeps recognized technical information, including capture settings; removes personal information and opaque blocks.",
                "custom": "Choose categories or individual fields. Only the current selection will be removed.",
            }
            self.description.setText(descriptions[profile])
            self.update_plan()

        def set_report(self, report):
            self.report = report
            self.updating = True
            self.tree.clear()
            if report:
                for entry in report.entries:
                    item = QTreeWidgetItem([entry.name, entry.source])
                    item.setData(0, Qt.ItemDataRole.UserRole, entry)
                    item.setToolTip(0, classify(entry).description)
                    if entry.action == REMOVE:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.CheckState.Checked if self.groups[classify(entry).group].isChecked() else Qt.CheckState.Unchecked)
                    else:
                        item.setText(0, entry.name + " · protected")
                    self.tree.addTopLevelItem(item)
            self.updating = False
            self.update_plan()

        def group_changed(self, group, checked):
            if self.updating:
                return
            self.updating = True
            for index in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(index)
                entry = item.data(0, Qt.ItemDataRole.UserRole)
                if entry.action == REMOVE and classify(entry).group == group:
                    item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.updating = False
            self.update_plan()

        def select(self, mode):
            for key, check in self.groups.items():
                check.setChecked(mode == "all" or (mode == "recommended" and key in RECOMMENDED))
            for key, check in self.groups.items():
                self.group_changed(key, check.isChecked())

        def options(self):
            profile = self.combo.currentData()
            if profile != "custom":
                return {"profile": profile}
            if self.report is not None and not self.batch:
                selected = []
                for index in range(self.tree.topLevelItemCount()):
                    item = self.tree.topLevelItem(index)
                    entry = item.data(0, Qt.ItemDataRole.UserRole)
                    if entry.action == REMOVE and item.checkState(0) == Qt.CheckState.Checked:
                        selected.append(entry.id)
                return {"profile": profile, "entry_ids": selected}
            return {"profile": profile, "groups": [key for key, check in self.groups.items() if check.isChecked()]}

        def update_plan(self, *args):
            if self.updating:
                return
            if not self.report:
                self.plan_label.setText("Rules will be applied to each image individually." if self.batch else
                                        "Select an image to review its fields and the planned action.")
                return
            options = self.options()
            policy = CleaningPolicy(options["profile"], frozenset(options.get("groups", ())), frozenset(options.get("entry_ids", ())))
            count = sum(policy(entry) for entry in self.report.entries)
            self.plan_label.setText(f"{count} fields will be removed · {len(self.report.entries) - count} preserved")

    class Page(QWidget):
        def __init__(self, window, is_scan: bool):
            super().__init__()
            self.setObjectName("Page")
            self.window, self.is_scan = window, is_scan
            self.path = None
            self.report = None
            self.result_path = None
            self.busy = False
            self.reveal_timer = QTimer(self)
            self.reveal_timer.setSingleShot(True)
            self.reveal_timer.timeout.connect(lambda: self.window.reveal_results(self))
            self.metadata_tree = None
            self.search = None
            self.filters = []
            self.active_filter = "All"
            layout = QVBoxLayout(self)
            layout.setContentsMargins(32, 28, 32, 28)
            layout.setSpacing(20)
            heading = QVBoxLayout()
            heading.setSpacing(7)
            heading.addWidget(label("Scan" if is_scan else "Quick clean", "Title"))
            heading.addWidget(label(
                "Inspect the metadata and AI references found in your file." if is_scan else
                "Remove metadata from your image without recompression.", "Subtitle", True))
            layout.addLayout(heading)
            if is_scan:
                self.quick_actions = QWidget()
                quick = QHBoxLayout(self.quick_actions)
                quick.setContentsMargins(0, 0, 0, 0)
                for title, callback in (("Scan folder", window.choose_folder),
                                        ("Batch", lambda: window.switch(3)),
                                        ("Quick clean", lambda: window.switch(0))):
                    action = button(title, "Quiet")
                    action.clicked.connect(callback)
                    quick.addWidget(action)
                quick.addStretch()
                layout.addWidget(self.quick_actions)

            work = QBoxLayout(QBoxLayout.Direction.LeftToRight)
            self.work = work
            work.setSpacing(20)
            source_card = QFrame()
            self.source_card = source_card
            source_card.setObjectName("Card")
            source_layout = QVBoxLayout(source_card)
            source_layout.setContentsMargins(18, 17, 18, 18)
            source_layout.setSpacing(15)
            source_heading = QHBoxLayout()
            source_heading.addWidget(label("Source image", "Section"))
            source_heading.addStretch()
            self.source_tag = label("NO FILE", "Tag")
            source_heading.addWidget(self.source_tag)
            source_layout.addLayout(source_heading)
            self.drop = DropZone()
            self.drop.selected.connect(self.select_file)
            self.drop.cleared.connect(self.reset_file)
            self.drop.invalid.connect(self.show_error)
            source_layout.addWidget(self.drop, 1)
            work.addWidget(source_card, 1)

            overview = QFrame()
            overview.setObjectName("Card")
            self.overview = overview
            overview.setFixedWidth(268)
            box = QVBoxLayout(overview)
            box.setContentsMargins(20, 19, 20, 18)
            box.setSpacing(15)
            box.addWidget(label("File overview", "Section"))
            self.facts = {}
            facts = QVBoxLayout()
            facts.setSpacing(12)
            for name in ("Format", "Dimensions", "Size"):
                row = QHBoxLayout()
                row.addWidget(label(name, "Muted"))
                row.addStretch()
                value = label("—", "FileTitle")
                value.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.facts[name] = value
                row.addWidget(value)
                facts.addLayout(row)
            box.addLayout(facts)
            box.addWidget(line())
            self.context = QWidget()
            context_layout = QVBoxLayout(self.context)
            context_layout.setContentsMargins(0, 0, 0, 0)
            context_layout.setSpacing(11)
            for text in (("Descriptive data", "AI references", "Technical information") if is_scan else
                         ("No recompression", "Color and orientation preserved", "Original unchanged")):
                row = QHBoxLayout()
                row.setSpacing(8)
                row.addWidget(icon_label("scan" if is_scan else "check", 14, "#74746b"))
                row.addWidget(label(text, "Muted", True))
                row.addStretch()
                context_layout.addLayout(row)
            box.addWidget(self.context)
            box.addStretch()
            self.action = button("Analyze metadata" if is_scan else "Remove metadata", "Primary")
            self.action.setMinimumHeight(43)
            self.action.setEnabled(False)
            self.action.clicked.connect(self.start_scan if is_scan else self.start_clean)
            box.addWidget(self.action)
            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.setTextVisible(False)
            self.progress.setFixedHeight(3)
            self.progress.hide()
            box.addWidget(self.progress)
            self.file_status = label("Select an image to continue.", "Small", True)
            self.file_status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            box.addWidget(self.file_status)
            work.addWidget(overview)
            layout.addLayout(work)
            if not is_scan:
                self.profile_panel = ProfileControls(window)
                layout.addWidget(self.profile_panel)

            info = QHBoxLayout()
            info.setSpacing(8)
            info.addWidget(icon_label("info", 15, "#8a8a80"))
            info.addWidget(label(
                "Scan reads metadata; it is not a visual AI detector." if is_scan else
                "Image format and data are preserved. A new copy is saved.", "Small", True), 1)
            more = button("Learn more", "Quiet")
            more.clicked.connect(window.show_about)
            info.addWidget(more)
            layout.addLayout(info)

            self.result_box = QWidget()
            self.results = QVBoxLayout(self.result_box)
            self.results.setContentsMargins(0, 0, 0, 0)
            self.results.setSpacing(16)
            self.result_box.hide()
            layout.addWidget(self.result_box)
            layout.addStretch()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if not hasattr(self, "work"):
                return
            narrow = self.width() < 720
            self.work.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
            self.overview.setMinimumWidth(0 if narrow else 268)
            self.overview.setMaximumWidth(16777215 if narrow else 268)
            margin = 24 if self.width() < 800 else 32
            self.layout().setContentsMargins(margin, 28, margin, 28)

        def show_error(self, text: str):
            QMessageBox.warning(self, "MetaWipe", text)

        def reset_file(self):
            if self.busy:
                return
            self.path = self.report = self.result_path = None
            self.window.explorer.hide()
            if not self.is_scan:
                self.profile_panel.set_report(None)
            self.drop.reset()
            self.source_tag.setText("NO FILE")
            for widget in self.facts.values():
                widget.setText("—")
            self.context.show()
            self.result_box.hide()
            self.action.setEnabled(False)
            self.file_status.setText("Select an image to continue.")
            self.window.status.setText("Ready")

        def select_file(self, path: str):
            if self.busy:
                return
            candidate = Path(path).expanduser()
            try:
                if not candidate.is_file():
                    raise MetadataError("The selected file does not exist.")
                if candidate.stat().st_size > MAX_FILE:
                    raise MetadataError("The per-image limit is 256 MiB.")
                format_name, dimensions = self.drop.set_path(candidate)
            except (OSError, MetadataError) as exc:
                self.show_error(str(exc))
                return
            self.path = candidate.resolve()
            self.report = self.result_path = None
            self.source_tag.setText(format_name[:12])
            self.facts["Format"].setText(format_name)
            self.facts["Dimensions"].setText(dimensions)
            self.facts["Size"].setText(human_size(candidate.stat().st_size))
            self.context.show()
            self.result_box.hide()
            self.action.setEnabled(True)
            self.file_status.setText("Ready to analyze." if self.is_scan else "A new copy will be saved.")
            self.window.status.setText("Image selected")
            if not self.is_scan:
                self.profile_panel.set_report(None)
                self.set_busy(True)
                def preview_ready(report):
                    self.set_busy(False)
                    self.report = report
                    self.profile_panel.set_report(report)
                    self.file_status.setText(privacy_summary(report))
                    self.window.status.setText("Analysis complete · profile ready")
                self.window.run_job(lambda emit: scan_image(self.path, progress=emit), preview_ready, self.fail, self.file_status.setText)

        def set_busy(self, busy: bool):
            self.busy = busy
            self.drop.setEnabled(not busy)
            if not self.is_scan:
                self.profile_panel.setEnabled(not busy)
            self.action.setEnabled(not busy and self.path is not None)
            self.progress.setVisible(busy)
            self.action.setText(("Analyzing…" if self.is_scan else "Processing…") if busy else
                                ("Analyze metadata" if self.is_scan else "Remove metadata"))
            if busy:
                self.file_status.setText("Analyzing file…" if self.is_scan else "Checking the integrity of the copy…")
                self.window.status.setText("Operation in progress")

        def fail(self, text: str):
            self.set_busy(False)
            self.file_status.setText("Could not complete the operation.")
            self.window.status.setText("Operation not completed")
            self.show_error(text)

        def start_scan(self):
            if self.path is None or self.busy:
                return
            path = self.path
            self.set_busy(True)
            self.window.run_job(lambda emit: scan_image(path, progress=emit), self.show_report, self.fail, self.file_status.setText)

        def start_clean(self):
            if self.path is None or self.busy:
                return
            source = self.path
            suffix = source.suffix.lower()
            suggestion = unique_output(source)
            destination, _ = QFileDialog.getSaveFileName(
                self, "Save cleaned copy", str(suggestion),
                f"Same format (*{suffix});;All files (*)",
                options=QFileDialog.Option.DontConfirmOverwrite)
            if not destination:
                return
            self.set_busy(True)
            options = self.profile_panel.options()
            if self.report:
                options["expected_hash"] = self.report.file_hash
            self.window.run_job(lambda emit: clean_image(source, destination, progress=emit, **options), self.show_clean, self.fail, self.file_status.setText)

        def clear_results(self):
            self.metadata_tree = None
            self.search = None
            self.filters = []
            while self.results.count():
                item = self.results.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.result_box.show()

        def show_clean(self, result: CleanResult):
            self.set_busy(False)
            self.clear_results()
            self.result_path = result.path
            self.window.last_clean = result
            self.window.record_report(result)
            self.window.compare_page.set_result(result)
            self.file_status.setText("Image saved successfully.")
            self.window.status.setText("Cleaning complete · saved copy verified" if result.verified else
                                       "Cleaning partially completed")
            card = QFrame()
            card.setObjectName("Card")
            box = QVBoxLayout(card)
            box.setContentsMargins(22, 22, 22, 22)
            box.setSpacing(16)
            box.addWidget(label("✓ Cleaning complete" if result.verified else "Cleaning partially completed", "ResultTitle", True))
            removed = sum(c.status == "REMOVED" for c in result.changes)
            box.addWidget(label(f"{removed} metadata fields removed · image data is identical", "Subtitle", True))
            box.addWidget(comparison_summary(result.before, result.after))
            if result.remaining:
                box.addWidget(label("Selected fields still present: " + ", ".join(result.remaining), "Muted", True))
            path_label = label(str(result.path), "Small", True)
            path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(path_label)
            actions = QWidget()
            row = QBoxLayout(QBoxLayout.Direction.LeftToRight, actions)
            for title, callback, glyph in (
                ("View changes", lambda: self.window.open_comparison(result), "sliders"),
                ("Inspect cleaned copy", lambda: self.window.inspect_output(result.path), "scan"),
                ("Open folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.path.parent))), "folder")):
                item = button(title, glyph=glyph)
                item.clicked.connect(callback)
                row.addWidget(item)
            box.addWidget(actions)
            self.results.addWidget(card)
            self.reveal_timer.start(150)

        def filter_entries(self):
            if self.metadata_tree is None or self.search is None:
                return
            query = self.search.text().casefold().strip()
            visible = 0
            for index in range(self.metadata_tree.topLevelItemCount()):
                item = self.metadata_tree.topLevelItem(index)
                entry = item.data(0, Qt.ItemDataRole.UserRole)
                matches_type = (self.active_filter == "All" or
                                (self.active_filter == "Removable" and entry.action == REMOVE) or
                                (self.active_filter == "Technical" and classify(entry).level == "Technical"))
                matches_text = query in " ".join((entry.name, entry.value, entry.source, entry.category)).casefold()
                item.setHidden(not (matches_type and matches_text))
                visible += matches_type and matches_text
            total = self.metadata_tree.topLevelItemCount()
            self.filtered_count.setText(f"{visible} of {total} metadata fields")
            self.table_stack.setCurrentIndex(0 if visible else 1)
            self.table_stack.setFixedHeight(self.metadata_tree.height() if visible else 200)
            self.empty_subtitle.setText("Try changing the search or filters." if total else
                                       "No additional metadata was found in this file.")
            self.metadata_tree.hover_changed(-1)
            current = self.metadata_tree.currentItem()
            if current and current.isHidden():
                self.metadata_tree.setCurrentItem(None)

        def choose_filter(self, value: str):
            self.active_filter = value
            self.segmented.select(value)
            self.filter_entries()

        def show_report(self, report: Report):
            self.set_busy(False)
            self.clear_results()
            self.report = report
            self.window.record_report(report)
            self.active_filter = "All"
            self.file_status.setText("Analysis complete.")
            self.window.status.setText("Scan complete")
            self.facts["Format"].setText(report.format)
            self.facts["Dimensions"].setText(f"{report.width} × {report.height} px")
            self.facts["Size"].setText(human_size(report.size))
            self.context.hide()
            self.drop.compact()

            frame = QWidget()
            box = QVBoxLayout(frame)
            box.setContentsMargins(0, 8, 0, 0)
            box.setSpacing(18)
            header = QHBoxLayout()
            header.setSpacing(14)
            title = label("Scan results", "ResultTitle", True)
            header.addWidget(title, 1)
            self.copy_button = CopyButton(report)
            header.addWidget(self.copy_button)
            box.addLayout(header)
            self.metric_grid = MetricGrid(report)
            box.addWidget(self.metric_grid)
            self.analysis_status = status_card(report)
            box.addWidget(self.analysis_status)

            self.search_field = SearchField()
            self.search = self.search_field.edit
            self.segmented = SegmentedControl()
            self.filters = self.segmented.buttons
            self.segmented.changed.connect(self.choose_filter)
            box.addWidget(ResponsiveRow(self.search_field, self.segmented))

            self.table_stack = ContentStack()
            tree = MetadataTree()
            self.metadata_tree = tree
            tree.setFixedHeight(min(330, max(180, 40 + 48 * len(report.entries))))
            self.table_stack.addWidget(tree)
            empty, self.empty_subtitle = empty_state()
            self.table_stack.addWidget(empty)
            box.addWidget(self.table_stack)

            for entry in report.entries:
                item = QTreeWidgetItem([entry.name, " ".join(entry.value.split())[:180], entry.source, entry.action])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                item.setToolTip(0, entry_tooltip(entry))
                item.setToolTip(1, "Select a row to view the full content.")
                item.setToolTip(2, entry.source)
                item.setToolTip(3, "This item can be removed from the new copy." if entry.action == REMOVE else
                                "This item is preserved to maintain the appearance of the image.")
                tree.addTopLevelItem(item)

            def show_entry(current, previous):
                if current is not None:
                    self.window.explorer.open_entry(current.data(0, Qt.ItemDataRole.UserRole))
            tree.currentItemChanged.connect(show_entry)
            count_row = QHBoxLayout()
            self.filtered_count = label("", "Small")
            count_row.addWidget(self.filtered_count)
            count_row.addStretch()
            count_row.addWidget(label("Select a row to view details", "Small"))
            box.addLayout(count_row)
            box.addWidget(label(
                "Cleaning saves a new copy. Technical items marked “Preserve” maintain the appearance of the image.",
                "Small", True))
            self.search.textChanged.connect(self.filter_entries)
            self.results.addWidget(frame)
            self.filter_entries()
            self.reveal_timer.start(180)


    class BatchJob(QThread):
        discovered = Signal(object)
        item_done = Signal(object, object, object)
        advanced = Signal(int, int, str, str)
        failed = Signal(str)
        outcome = Signal(str)

        def __init__(self, paths, operation, parent, recursive=False, output=None, clean_options=None):
            super().__init__(parent)
            self.paths, self.operation = paths, operation
            self.recursive, self.output = recursive, output
            self.clean_options = clean_options or {}

        def run(self):
            try:
                cancel = self.isInterruptionRequested
                if self.operation == "discover":
                    self.discovered.emit(list(discover(self.paths, self.recursive, cancel)))
                else:
                    for item, report, result in process_batch(self.paths, self.operation, self.output,
                            cancel=cancel, progress=self.advanced.emit, clean_options=self.clean_options):
                        self.item_done.emit(item, report, result)
                self.outcome.emit("Complete")
            except Cancelled:
                self.outcome.emit("Canceled · completed results have been preserved")
            except Exception as exc:
                self.failed.emit(str(exc))

    class BatchPage(QWidget):
        def __init__(self, window):
            super().__init__()
            self.window, self.busy, self.job = window, False, None
            self.records = {}
            self.rows = {}
            self.followup_timer = QTimer(self)
            self.followup_timer.setSingleShot(True)
            self.followup_timer.timeout.connect(lambda: self.start("scan"))
            self.setObjectName("Page")
            box = QVBoxLayout(self)
            box.setContentsMargins(32, 28, 32, 28)
            box.setSpacing(18)
            box.addWidget(label("Batch & folders", "Title"))
            box.addWidget(label("Analyze and clean multiple images. Every original is preserved.", "Subtitle", True))
            self.controls = QWidget()
            grid = QGridLayout(self.controls)
            grid.setContentsMargins(0, 0, 0, 0)
            self.add_files = button("Add images", glyph="image")
            self.add_folder = button("Scan folder", glyph="folder")
            self.recursive = QCheckBox("Include subfolders")
            self.add_files.clicked.connect(self.browse)
            self.add_folder.clicked.connect(self.folder)
            grid.addWidget(self.add_files, 0, 0)
            grid.addWidget(self.add_folder, 0, 1)
            grid.addWidget(self.recursive, 1, 0, 1, 2)
            box.addWidget(self.controls)
            self.summary = label("Add images or a folder to get started.", "Subtitle", True)
            self.summary.setMinimumHeight(60)
            box.addWidget(self.summary)
            self.tree = QTreeWidget()
            self.tree.setHeaderLabels(["FILE", "METADATA", "PRIVACY", "STATUS", "ACTION"])
            self.tree.setRootIsDecorated(False)
            self.tree.setUniformRowHeights(True)
            self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.tree.setMinimumHeight(270)
            self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for i, width in ((1, 105), (2, 165), (3, 100), (4, 60)):
                self.tree.setColumnWidth(i, width)
            self.tree.itemClicked.connect(lambda item, column: self.inspect(item) if column == 4 else None)
            self.tree.itemDoubleClicked.connect(lambda item, column: self.inspect(item))
            self.tree.setToolTip("Use Ctrl or Shift to select multiple images. Click View to open Scan.")
            box.addWidget(self.tree)
            self.profile_panel = ProfileControls(window, batch=True)
            box.addWidget(self.profile_panel)
            self.operations = QWidget()
            actions = QGridLayout(self.operations)
            actions.setContentsMargins(0, 0, 0, 0)
            self.scan_all = button("Analyze all", "Primary", "scan")
            self.clean_selected = button("Clean selected", glyph="clean")
            self.clean_all = button("Clean all", glyph="clean")
            self.clear = button("Clear list", "Quiet", "close")
            self.scan_all.clicked.connect(lambda: self.start("scan"))
            self.clean_all.clicked.connect(lambda: self.start("clean"))
            self.clean_selected.clicked.connect(lambda: self.start("clean", True))
            self.clear.clicked.connect(self.clear_list)
            actions.addWidget(self.scan_all, 0, 0)
            actions.addWidget(self.clean_selected, 0, 1)
            actions.addWidget(self.clean_all, 1, 0)
            actions.addWidget(self.clear, 1, 1)
            box.addWidget(self.operations)
            self.progress = QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFixedHeight(18)
            box.addWidget(self.progress)
            self.status = label("Ready", "Small", True)
            box.addWidget(self.status)
            self.cancel = button("Cancel", glyph="close")
            self.cancel.setEnabled(False)
            self.cancel.clicked.connect(self.request_cancel)
            box.addWidget(self.cancel, alignment=Qt.AlignmentFlag.AlignLeft)
            box.addWidget(label("The privacy summary refers to the original files analyzed. Select View to inspect a file.", "Small", True))
            box.addStretch()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if hasattr(self, "summary"):
                self.summary.setMinimumHeight(max(60, self.summary.heightForWidth(max(100, self.width() - 64))))

        def clear_list(self):
            if self.busy:
                return
            self.records.clear()
            self.rows.clear()
            self.tree.clear()
            self.update_summary()
            self.progress.setValue(0)

        def browse(self):
            paths, _ = QFileDialog.getOpenFileNames(self, "Select images", "", "Images (*.png *.apng *.jpg *.jpeg *.jpe *.webp);;All files (*)")
            if paths:
                self.load_paths(paths)

        def folder(self):
            path = QFileDialog.getExistingDirectory(self, "Scan folder")
            if path:
                self.load_paths([path], auto_scan=True)

        def load_paths(self, paths, auto_scan=False):
            if self.busy:
                return
            self.auto_scan = auto_scan
            self.launch(BatchJob(paths, "discover", self.window, self.recursive.isChecked()))
            self.status.setText("Looking for images in the folder…")
            self.progress.setRange(0, 0)

        def loaded(self, paths):
            for path in paths:
                key = str(path)
                if key not in self.records:
                    self.records[key] = BatchItem(key)
                    row = QTreeWidgetItem([path.name, "—", "Pending", "Pending", "View"])
                    row.setData(0, Qt.ItemDataRole.UserRole, key)
                    row.setToolTip(0, key)
                    row.setSizeHint(0, QSize(0, 44))
                    self.tree.addTopLevelItem(row)
                    self.rows[key] = row
            self.update_summary()

        def update_summary(self):
            info = batch_summary(list(self.records.values()))
            self.summary.setText(f'{info["files"]} images · {info["analysed"]} analyzed · {info["pending"]} pending · {info["errors"]} errors\n'
                f'{info["with_sensitive_metadata"]} with sensitive/potentially sensitive information · '
                f'{info["with_gps"]} with GPS · {info["with_device"]} with device information')

        def start(self, operation, selected=False):
            if self.busy:
                return
            paths = ([item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()] if selected else list(self.records))
            if not paths:
                QMessageBox.information(self, "Batch", "Select at least one image." if selected else "Add images to the list.")
                return
            output = None
            if operation == "clean":
                output = QFileDialog.getExistingDirectory(self, "Folder for cleaned copies")
                if not output:
                    return
            self.auto_scan = False
            self.launch(BatchJob(paths, operation, self.window, output=output, clean_options=self.profile_panel.options()))

        def launch(self, job):
            self.busy, self.job = True, job
            self.controls.setEnabled(False)
            self.operations.setEnabled(False)
            self.profile_panel.setEnabled(False)
            self.cancel.setEnabled(True)
            self.window.jobs.append(job)
            job.discovered.connect(self.loaded)
            job.item_done.connect(self.received)
            job.advanced.connect(self.advanced)
            job.outcome.connect(self.status.setText)
            job.failed.connect(lambda error: self.status.setText("Error: " + error))
            def finished():
                self.busy = False
                self.controls.setEnabled(True)
                self.operations.setEnabled(True)
                self.profile_panel.setEnabled(True)
                self.cancel.setEnabled(False)
                if self.progress.maximum() == 0:
                    self.progress.setRange(0, 100)
                    self.progress.setValue(0)
                self.window.jobs.remove(job)
                self.job = None
                self.window.reports_page.set_report(list(self.records.values()))
                if job.operation == "clean" and self.window.last_clean:
                    self.window.compare_page.set_result(self.window.last_clean)
                job.deleteLater()
                if getattr(self, "auto_scan", False) and self.records and not job.isInterruptionRequested():
                    self.auto_scan = False
                    self.followup_timer.start(0)
            job.finished.connect(finished)
            job.start()

        def advanced(self, done, total, name, stage):
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(done)
            self.status.setText(f"{done} / {total} · {name} · {stage}")

        def received(self, item, report, result):
            self.records[item.file] = item
            row = self.rows[item.file]
            row.setText(1, str(item.metadata_count) if item.metadata_count is not None else "—")
            row.setText(2, f"{item.sensitive_count} sensitive · {item.potentially_sensitive_count} potential" if item.metadata_count is not None else "Pending")
            row.setText(3, item.status)
            row.setToolTip(3, item.error or ("Remaining fields: " + ", ".join(item.remaining or []) if item.status == "Partial" else item.status))
            self.update_summary()
            if report:
                self.window.record_report(result or report, update_reports=False)
            if result:
                self.window.last_clean = result

        def request_cancel(self):
            if self.job:
                self.job.requestInterruption()
                self.cancel.setEnabled(False)
                self.status.setText("Canceling safely…")

        def inspect(self, item):
            record = self.records[item.data(0, Qt.ItemDataRole.UserRole)]
            if not record.output:
                self.window.inspect_output(Path(record.file))
                return
            menu = QMenu(self)
            menu.addAction("Inspect original", lambda: self.window.inspect_output(Path(record.file)))
            menu.addAction("Inspect copy", lambda: self.window.inspect_output(Path(record.output)))
            menu.addAction("View changes", lambda: self.window.compare_paths(record.file, record.output))
            rectangle = self.tree.visualItemRect(item)
            menu.exec(self.tree.viewport().mapToGlobal(rectangle.bottomLeft()))

    def comparison_summary(before, after):
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(14)
        for column, heading in enumerate(("", "BEFORE", "AFTER")):
            grid.addWidget(label(heading, "Eyebrow"), 0, column)
        bc, ac = privacy_counts(before), privacy_counts(after)
        values = (("Size", human_size(before.size), human_size(after.size)),
                  ("Metadata", str(len(before.entries)), str(len(after.entries))),
                  ("Sensitive", str(bc["sensitive_count"]), str(ac["sensitive_count"])),
                  ("Potentially sensitive", str(bc["potentially_sensitive_count"]), str(ac["potentially_sensitive_count"])),
                  ("Format", before.format, after.format))
        for row, values_row in enumerate(values, 1):
            for column, text in enumerate(values_row):
                grid.addWidget(label(text, "Muted" if column == 0 else "FileTitle", True), row, column)
        return widget

    class ComparePage(QWidget):
        def __init__(self, window):
            super().__init__()
            self.window = window
            self.setObjectName("Page")
            self.busy = False
            self.result = None
            box = QVBoxLayout(self)
            box.setContentsMargins(32, 28, 32, 28)
            box.setSpacing(20)
            box.addWidget(label("Compare metadata", "Title"))
            box.addWidget(label("See exactly what was removed, preserved or changed.", "Subtitle", True))
            self.choose = button("Choose two images", glyph="folder")
            self.choose.clicked.connect(self.choose_pair)
            box.addWidget(self.choose, alignment=Qt.AlignmentFlag.AlignLeft)
            self.body = QWidget()
            self.content = QVBoxLayout(self.body)
            self.content.setContentsMargins(0, 0, 0, 0)
            self.content.setSpacing(20)
            self.content.addWidget(label("Clean an image or choose the original and its copy to compare.", "Muted", True))
            box.addWidget(self.body)
            box.addStretch()

        def choose_pair(self):
            if self.busy:
                return
            first, _ = QFileDialog.getOpenFileName(self, "Before · choose original", "", "Images (*.png *.apng *.jpg *.jpeg *.webp)")
            if not first:
                return
            second, _ = QFileDialog.getOpenFileName(self, "After · choose copy", str(Path(first).parent), "Images (*.png *.apng *.jpg *.jpeg *.webp)")
            if not second:
                return
            self.busy = True
            self.choose.setEnabled(False)
            def done(pair):
                self.busy = False
                self.choose.setEnabled(True)
                self.render(*pair)
            def fail(error):
                self.busy = False
                self.choose.setEnabled(True)
                QMessageBox.warning(self, "Comparison", error)
            self.window.run_job(lambda: (scan_image(first), scan_image(second)), done, fail)

        def set_result(self, result):
            self.result = result
            self.render(result.before, result.after, result)

        def render(self, before, after, result=None):
            while self.content.count():
                item = self.content.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.content.addWidget(label(Path(before.path).name + "  →  " + Path(after.path).name, "Section", True))
            self.content.addWidget(comparison_summary(before, after))
            changes = metadata_diff(before, after)
            removed = sum(c.status == "REMOVED" for c in changes)
            self.content.addWidget(label(f"{removed} metadata fields removed", "Section"))
            note = ("Image and display data are identical." if before.image_hash == after.image_hash else
                    "Image/display data differs between these files.")
            if result:
                note += " Image saved successfully." if result.verified else " Cleaning partially completed: " + ", ".join(result.remaining)
            self.content.addWidget(label(note, "Muted", True))
            tree = MetadataTree()
            tree.setHeaderLabels(["FIELD", "BEFORE → AFTER", "SOURCE", "STATUS"])
            tree.setMinimumHeight(320)
            for c in changes:
                value = c.before if c.status == "PRESERVED" else f"{c.before or '—'} → {c.after or '—'}"
                item = QTreeWidgetItem([c.name, " ".join(value.split())[:180], c.source, c.status])
                item.setToolTip(1, value[:16000])
                tree.addTopLevelItem(item)
            details = QPlainTextEdit()
            details.setReadOnly(True)
            details.setMaximumHeight(150)
            details.hide()
            def show_diff(item, previous):
                if item is not None:
                    details.setPlainText(item.text(0) + " · " + item.text(3) + "\n\n" + item.toolTip(1))
                    details.show()
            tree.currentItemChanged.connect(show_diff)
            self.content.addWidget(tree)
            self.content.addWidget(details)
            self.tree = tree

    class ReportsPage(QWidget):
        def __init__(self, window):
            super().__init__()
            self.setObjectName("Page")
            self.value = None
            box = QVBoxLayout(self)
            box.setContentsMargins(32, 28, 32, 28)
            box.setSpacing(18)
            box.addWidget(label("Reports", "Title"))
            box.addWidget(label("Export the latest scan, clean or batch summary from this session.", "Subtitle", True))
            box.addWidget(label("Reports may include file paths and personal values found in metadata. "
                                "They are saved only to the location you choose.", "Small", True))
            self.summary = label("Analyze an image to create a report.", "Section", True)
            box.addWidget(self.summary)
            self.actions = QWidget()
            self.action_box = QVBoxLayout(self.actions)
            self.action_box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(self.actions)
            self.preview = QPlainTextEdit()
            self.preview.setReadOnly(True)
            self.preview.setMinimumHeight(320)
            self.preview.setPlaceholderText("Your report will appear here after analysis.")
            box.addWidget(self.preview)
            box.addStretch()

        def set_report(self, value):
            self.value = value
            title = (Path(value.path).name if isinstance(value, Report) else
                     Path(value.before.path).name if isinstance(value, CleanResult) else f"{len(value)} images · resumo of lote")
            self.summary.setText(title)
            while self.action_box.count():
                self.action_box.takeAt(0).widget().deleteLater()
            self.export_button = CopyButton(value)
            self.action_box.addWidget(self.export_button, alignment=Qt.AlignmentFlag.AlignLeft)
            preview = render_report(value)
            self.preview.setPlainText(preview[:80000] + ("\n[Preview shortened; the export includes the full report.]" if len(preview) > 80000 else ""))

    class HistoryPage(QWidget):
        def __init__(self, window):
            super().__init__()
            self.window = window
            self.setObjectName("Page")
            box = QVBoxLayout(self)
            box.setContentsMargins(32, 28, 32, 28)
            box.setSpacing(18)
            box.addWidget(label("Local history", "Title"))
            box.addWidget(label("Optional. Stores only filename, operation, counts and time. "
                                "Does not store images, full paths or metadata values.", "Subtitle", True))
            self.toggle = QCheckBox("Save history on this computer")
            self.toggle.setChecked(window.history.enabled)
            self.toggle.toggled.connect(self.toggle_history)
            box.addWidget(self.toggle)
            self.clear = button("Clear history", glyph="clean")
            self.clear.clicked.connect(self.clear_history)
            box.addWidget(self.clear, alignment=Qt.AlignmentFlag.AlignLeft)
            self.status = label("", "Small", True)
            box.addWidget(self.status)
            self.tree = QTreeWidget()
            self.tree.setHeaderLabels(["WHEN", "FILE", "OPERATION", "METADATA", "REMOVED"])
            self.tree.setRootIsDecorated(False)
            self.tree.setMinimumHeight(340)
            self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.tree.setColumnWidth(0, 175)
            box.addWidget(self.tree)
            box.addStretch()
            self.refresh()

        def toggle_history(self, enabled):
            self.window.history.enabled = enabled
            self.window.settings.setValue("privacy/history", enabled)
            self.refresh()

        def clear_history(self):
            try:
                self.window.history.clear()
                self.refresh()
            except Exception as exc:
                self.status.setText("Could not clear history: " + str(exc))

        def refresh(self):
            from datetime import datetime
            self.tree.clear()
            try:
                records = self.window.history.list()
                for record in records:
                    at = datetime.fromisoformat(record["at"])
                    date = "Today" if at.date() == datetime.now().astimezone().date() else at.strftime("%d/%m/%Y")
                    self.tree.addTopLevelItem(QTreeWidgetItem([date + " · " + at.strftime("%H:%M"), record["file"],
                        {"Limpeza": "Clean"}.get(record["operation"], record["operation"]),
                        str(record["metadata_count"]), str(record["removed_count"])]))
                self.status.setText(("Enabled" if self.window.history.enabled else "Disabled") +
                                    f" · {len(records)} local records. Turning history off does not delete existing records.")
            except Exception as exc:
                self.status.setText("Could not read history: " + str(exc))

    class SettingsPage(QWidget):
        def __init__(self, window):
            super().__init__()
            self.window = window
            self.setObjectName("Page")
            box = QVBoxLayout(self)
            box.setContentsMargins(32, 28, 32, 28)
            box.setSpacing(20)
            box.addWidget(label("Settings", "Title"))
            box.addWidget(label("Local preferences", "Subtitle"))
            box.addWidget(label("Default cleaning profile", "Section"))
            self.profile = QComboBox()
            for key, title in PROFILE_LABELS.items():
                self.profile.addItem(title, key)
            self.profile.setCurrentIndex(max(0, self.profile.findData(window.settings.value("clean/profile", "privacy"))))
            self.profile.currentIndexChanged.connect(self.profile_changed)
            box.addWidget(self.profile)
            self.recursive = QCheckBox("Include subfolders by default")
            self.recursive.setChecked(window.settings.value("scan/recursive", False, type=bool))
            self.recursive.toggled.connect(self.recursive_changed)
            box.addWidget(self.recursive)
            box.addWidget(label("Originals are protected", "Section"))
            box.addWidget(label("Cleaning always saves a copy with the _clean suffix. If the name exists, "
                                "a number is added. Overwriting originals is disabled.", "Muted", True))
            box.addWidget(label("Local processing", "Section"))
            box.addWidget(label("No uploads, analytics or tracking. History is off by default "
                                "and can be enabled or cleared in History. Change the theme at the top of the window.", "Muted", True))
            box.addWidget(label("The default profile takes effect next time you open the app; the current selection stays unchanged.", "Small", True))
            box.addStretch()

        def profile_changed(self):
            self.window.settings.setValue("clean/profile", self.profile.currentData())

        def recursive_changed(self, checked):
            self.window.settings.setValue("scan/recursive", checked)
            if not self.window.batch_page.busy:
                self.window.batch_page.recursive.setChecked(checked)

    class DetailPanel(QFrame):
        """Side inspector shared by Scan and batch results."""
        def __init__(self, window):
            super().__init__(window.centralWidget())
            self.window = window
            self.setObjectName("Card")
            self.setAutoFillBackground(True)
            self.motion = Tween(self, QRectF(), self.move_panel)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(22, 22, 22, 22)
            close = button("Close details", "Quiet", "close")
            close.clicked.connect(self.hide)
            outer.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            body = QWidget()
            self.fields = QVBoxLayout(body)
            self.fields.setContentsMargins(0, 0, 0, 0)
            self.fields.setSpacing(12)
            self.title = label("", "ResultTitle", True)
            self.fields.addWidget(self.title)
            self.value = QPlainTextEdit()
            self.value.setReadOnly(True)
            self.value.setMinimumHeight(140)
            self.fields.addWidget(label("VALUE", "Eyebrow"))
            self.fields.addWidget(self.value)
            self.labels = {}
            for key in ("Source", "Category", "What does it mean?", "Privacy", "Action"):
                self.fields.addWidget(label(key.upper(), "Eyebrow"))
                self.labels[key] = label("", "Muted", True)
                self.labels[key].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.fields.addWidget(self.labels[key])
            self.fields.addStretch()
            scroll.setWidget(body)
            outer.addWidget(scroll)
            self.hide()

        def move_panel(self, rect):
            self.setGeometry(rect.toRect())

        def reposition(self):
            area = self.parentWidget().rect()
            width = min(380, area.width() - 88)
            self.setGeometry(area.width() - width - 12, 72, width, max(300, area.height() - 114))

        def open_entry(self, entry):
            c = classify(entry)
            self.title.setText(entry.name)
            self.value.setPlainText(entry.value + ("\n[Displayed value truncated]" if entry.truncated else ""))
            for key, value in (("Source", entry.source), ("Category", c.level),
                               ("What does it mean?", c.description), ("Privacy", c.privacy),
                               ("Action", entry.action + (" · required for correct display" if entry.action == KEEP else
                               " · available in cleaning profiles"))):
                self.labels[key].setText(value)
            visible = self.isVisible()
            self.reposition()
            target = QRectF(self.geometry())
            if not visible:
                self.motion.to(target.translated(target.width(), 0), False)
            self.show()
            self.raise_()
            self.motion.to(target)

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.jobs = []
            self.settings = settings if settings is not None else QSettings("MetaWipe", "MetaWipe")
            if settings is None and not self.settings.allKeys():
                legacy = QSettings("PixelGuard", "PixelGuard")
                for key in ("appearance/theme", "privacy/history", "clean/profile", "scan/recursive"):
                    if legacy.contains(key):
                        self.settings.setValue(key, legacy.value(key))
                self.settings.setValue("app/initialized", True)
                self.settings.sync()
            self.history = HistoryStore(enabled=self.settings.value("privacy/history", False, type=bool))
            self.setWindowTitle("MetaWipe")
            self.setAcceptDrops(True)
            self.resize(1200, 830)
            self.setMinimumSize(640, 560)
            self.setStyleSheet(make_stylesheet())
            app_mark = QPixmap(256, 256)
            app_mark.fill(Qt.GlobalColor.transparent)
            painter = QPainter(app_mark)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(token("logo_bg")))
            painter.drawRoundedRect(QRectF(0, 0, 256, 256), 72, 72)
            painter.drawPixmap(42, 42, symbol("brand", 172, "logo_fg"))
            painter.end()
            self.setWindowIcon(QIcon(app_mark))
            central = QWidget()
            central.setObjectName("Shell")
            self.setCentralWidget(central)
            outer = QHBoxLayout(central)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            sidebar = QFrame()
            self.sidebar = sidebar
            sidebar.setObjectName("Sidebar")
            sidebar.setFixedWidth(224)
            side = QVBoxLayout(sidebar)
            self.side_layout = side
            side.setContentsMargins(14, 23, 14, 17)
            side.setSpacing(8)
            brand = QHBoxLayout()
            brand.setSpacing(10)
            logo = label("", "Logo")
            logo.setFixedSize(31, 31)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(symbol("brand", 21, "logo_fg"))
            logo.setProperty("theme_symbol", ("brand", 21, "logo_fg"))
            logo.setAccessibleName("MetaWipe logo")
            brand.addWidget(logo)
            self.brand_name = label("MetaWipe", "Brand")
            brand.addWidget(self.brand_name)
            brand.addStretch()
            side.addLayout(brand)
            side.addSpacing(18)
            self.nav = []
            for index, (text, glyph) in enumerate((("Quick clean", "clean"), ("Scan", "scan"), ("Compare", "sliders"), ("Batch & folders", "folder"), ("Reports", "copy"), ("History", "tag"), ("Settings", "sliders"))):
                nav_button = button("  " + text, "Nav", glyph)
                nav_button.setCheckable(True)
                nav_button.setAccessibleName(text)
                nav_button.setToolTip(text + (" · Ctrl+" + str(index + 1) if index < 2 else ""))
                nav_button.clicked.connect(lambda checked=False, i=index: self.switch(i))
                self.nav.append(nav_button)
            nav_content = QWidget()
            nav_content.setObjectName("NavigationContent")
            nav_layout = QVBoxLayout(nav_content)
            nav_layout.setContentsMargins(0, 0, 0, 0)
            nav_layout.setSpacing(6)
            self.category_labels = []
            for title, indices in (("SCAN", (1, 3)), ("CLEAN", (0,)), ("TOOLS", (2, 4, 5)), ("SETTINGS", (6,))):
                heading = label(title, "NavigationHeading")
                self.category_labels.append(heading)
                nav_layout.addWidget(heading)
                for index in indices:
                    nav_layout.addWidget(self.nav[index])
                nav_layout.addSpacing(8)
            nav_layout.addStretch()
            nav_scroll = QScrollArea()
            nav_scroll.setObjectName("NavigationScroll")
            nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
            nav_scroll.viewport().setObjectName("NavigationViewport")
            nav_scroll.viewport().setAutoFillBackground(False)
            nav_scroll.setWidgetResizable(True)
            nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            nav_scroll.setWidget(nav_content)
            nav_content.setAutoFillBackground(False)
            self.navigation_panel = QFrame()
            self.navigation_panel.setObjectName("NavigationPanel")
            self.navigation_layout = QVBoxLayout(self.navigation_panel)
            self.navigation_layout.setContentsMargins(7, 9, 7, 9)
            self.navigation_layout.setSpacing(0)
            self.navigation_layout.addWidget(nav_scroll)
            side.addWidget(self.navigation_panel, 1)
            about = button("  About", "Nav", "info")
            self.about_button = about
            about.setToolTip("About")
            about.setAccessibleName("About")
            about.clicked.connect(self.show_about)
            side.addWidget(about)
            side.addSpacing(10)
            side.addWidget(line())
            side.addSpacing(7)
            self.side_footer = QWidget()
            footer = QHBoxLayout(self.side_footer)
            footer.setContentsMargins(0, 0, 0, 0)
            footer.addWidget(label("MetaWipe", "Small"))
            footer.addStretch()
            footer.addWidget(label("v" + VERSION, "Small"))
            side.addWidget(self.side_footer)
            outer.addWidget(sidebar)

            right = QVBoxLayout()
            right.setContentsMargins(0, 0, 0, 0)
            right.setSpacing(0)
            toolbar = QFrame()
            toolbar.setObjectName("Toolbar")
            toolbar.setFixedHeight(60)
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(30, 0, 28, 0)
            toolbar_layout.setSpacing(14)
            self.toolbar_prefix = label("Tools  /", "Muted")
            toolbar_layout.addWidget(self.toolbar_prefix)
            self.breadcrumb = label("Quick clean", "FileTitle")
            toolbar_layout.addWidget(self.breadcrumb)
            toolbar_layout.addStretch()
            toolbar_layout.addWidget(icon_label("shield", 15, "#87877b"))
            self.local_label = label("Local processing", "Small")
            toolbar_layout.addWidget(self.local_label)
            self.theme_button = button("Light mode", glyph="sun")
            self.theme_button.setCheckable(True)
            self.theme_button.setAccessibleName("Switch to dark mode")
            self.theme_button.setToolTip("Switch between light and dark mode")
            self.theme_button.clicked.connect(lambda checked: self.apply_theme(checked))
            toolbar_layout.addWidget(self.theme_button)
            right.addWidget(toolbar)
            self.stack = QStackedWidget()
            self.last_clean = None
            self.compare_page = ComparePage(self)
            self.batch_page = BatchPage(self)
            self.reports_page = ReportsPage(self)
            self.history_page = HistoryPage(self)
            self.settings_page = SettingsPage(self)
            self.batch_page.recursive.setChecked(self.settings.value("scan/recursive", False, type=bool))
            self.pages = [Page(self, False), Page(self, True), self.compare_page, self.batch_page,
                          self.reports_page, self.history_page, self.settings_page]
            for page in self.pages:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setWidget(page)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.stack.addWidget(scroll)
            right.addWidget(self.stack, 1)
            footer_bar = QFrame()
            footer_bar.setObjectName("Footer")
            footer_bar.setFixedHeight(50)
            footer_layout = QHBoxLayout(footer_bar)
            footer_layout.setContentsMargins(30, 0, 26, 0)
            self.status = label("Ready", "Small")
            footer_layout.addWidget(self.status)
            footer_layout.addStretch()
            footer_layout.addWidget(label("PNG  ·  JPEG  ·  WebP", "Small"))
            right.addWidget(footer_bar)
            outer.addLayout(right, 1)
            for page in self.pages[:2]:
                page.drop.setAcceptDrops(False)
            self.overlay = QFrame(self.centralWidget())
            self.overlay.setObjectName("Card")
            self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            drop_layout = QVBoxLayout(self.overlay)
            drop_layout.addStretch()
            drop_layout.addWidget(icon_label("upload", 38, "accent"), alignment=Qt.AlignmentFlag.AlignHCenter)
            self.drop_message = label("Drop to analyze", "Title", True)
            self.drop_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            drop_layout.addWidget(self.drop_message)
            supported = label("JPG · JPEG · PNG · WebP", "Muted")
            supported.setAlignment(Qt.AlignmentFlag.AlignCenter)
            drop_layout.addWidget(supported)
            drop_layout.addStretch()
            self.overlay_effect = QGraphicsOpacityEffect(self.overlay)
            self.overlay.setGraphicsEffect(self.overlay_effect)
            self.overlay_fade = Tween(self, 0.0, self.overlay_effect.setOpacity)
            self.overlay.hide()
            self.explorer = DetailPanel(self)
            self.local_label.setToolTip("Images are analyzed locally and are not sent to servers.")
            self.switch(1)
            self.shortcuts = []
            for sequence, action in ((QKeySequence.StandardKey.Open, self.open_current),
                                     (QKeySequence("Ctrl+1"), lambda: self.switch(0)),
                                     (QKeySequence("Ctrl+2"), lambda: self.switch(1)),
                                     (QKeySequence("Ctrl+K"), self.focus_search)):
                shortcut = QShortcut(sequence, self)
                shortcut.activated.connect(action)
                self.shortcuts.append(shortcut)
            self.apply_theme(self.settings.value("appearance/theme", "dark") == "dark", persist=False)

        def apply_theme(self, dark: bool, persist: bool = True):
            theme_state["dark"] = bool(dark)
            themed_palette = QPalette()
            for role, key in (
                (QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"),
                (QPalette.ColorRole.Base, "card"), (QPalette.ColorRole.AlternateBase, "elevated"),
                (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "card"),
                (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "selection"),
                (QPalette.ColorRole.HighlightedText, "text"), (QPalette.ColorRole.PlaceholderText, "muted"),
                (QPalette.ColorRole.ToolTipBase, "elevated"), (QPalette.ColorRole.ToolTipText, "text"),
            ):
                themed_palette.setColor(role, QColor(token(key)))
            application.setPalette(themed_palette)
            application.setEffectEnabled(Qt.UIEffect.UI_FadeTooltip, True)
            self.setStyleSheet(make_stylesheet())
            self.theme_button.setChecked(dark)
            self.theme_button.setText("Light mode" if dark else "Dark mode")
            self.theme_button.setProperty("theme_symbol", ("sun" if dark else "moon", 16, "secondary_text"))
            self.theme_button.setAccessibleName("Switch to light mode" if dark else "Switch to dark mode")
            for widget in self.findChildren(QWidget):
                spec = widget.property("theme_symbol")
                if spec:
                    if isinstance(widget, QLabel):
                        widget.setPixmap(symbol(*spec))
                    elif isinstance(widget, QPushButton):
                        widget.setIcon(QIcon(symbol(*spec)))
                widget.update()
            self.switch(self.stack.currentIndex())
            if persist:
                self.settings.setValue("appearance/theme", "dark" if dark else "light")
                self.settings.sync()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if not hasattr(self, "side_footer"):
                return
            if hasattr(self, "explorer") and self.explorer.isVisible():
                self.explorer.reposition()
            compact = self.width() < 1040
            self.sidebar.setFixedWidth(72 if compact else 224)
            self.side_layout.setContentsMargins(10 if compact else 14, 23, 10 if compact else 14, 17)
            self.navigation_layout.setContentsMargins(4 if compact else 7, 9, 4 if compact else 7, 9)
            for widget in (self.brand_name, self.side_footer, *self.category_labels):
                widget.setVisible(not compact)
            for item, text in zip(self.nav + [self.about_button], ("Quick clean", "Scan", "Compare", "Batch & folders", "Reports", "History", "Settings", "About")):
                item.setText("" if compact else "  " + text)
                item.setMinimumWidth(0)
            self.local_label.setVisible(self.width() >= 800)
            self.toolbar_prefix.setVisible(self.width() >= 760)

        def reveal_results(self, page):
            if page is self.pages[self.stack.currentIndex()] and page.result_box.isVisible():
                self.stack.currentWidget().verticalScrollBar().setValue(max(0, page.result_box.y() - 24))

        def focus_search(self):
            page = self.pages[self.stack.currentIndex()]
            if getattr(page, "search", None) is not None and page.result_box.isVisible():
                self.stack.currentWidget().ensureWidgetVisible(page.search, 0, 24)
                page.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
                page.search.selectAll()

        def open_current(self):
            page = self.pages[self.stack.currentIndex()]
            if hasattr(page, "drop") and not page.busy:
                page.drop.browse()

        def show_about(self):
            QMessageBox.information(self, "About MetaWipe",
                "MetaWipe removes metadata embedded in PNG, JPEG and WebP without recompressing the image. "
                "Data required for correct display, such as orientation and color profiles, is preserved.\n\n"
                "Scan looks for fields and textual references. It is not a visual AI detector and does not validate C2PA signatures. "
                "Removing metadata does not remove pixel watermarks or guarantee that platforms will stop identifying AI content.\n\n"
                "Everything is processed on this computer. Images are not sent to servers.\n\n"
                "Shortcuts: Ctrl+O to choose an image; Ctrl+1 and Ctrl+2 to switch sections; Ctrl+K to search in Scan.")

        def switch(self, index: int):
            if hasattr(self, "explorer"):
                self.explorer.hide()
            self.stack.setCurrentIndex(index)
            if index == 5:
                self.history_page.refresh()
            self.breadcrumb.setText(("Quick clean", "Scan", "Compare", "Batch & folders", "Reports", "History", "Settings")[index])
            for i, nav_button in enumerate(self.nav):
                nav_button.setChecked(i == index)
                nav_button.update()

        def choose_folder(self):
            self.switch(3)
            self.batch_page.folder()

        def record_report(self, value, update_reports=True):
            if update_reports:
                self.reports_page.set_report(value)
            try:
                if isinstance(value, CleanResult):
                    self.history.add(value.before.path, "Clean", len(value.before.entries),
                                     sum(c.status == "REMOVED" for c in value.changes))
                else:
                    self.history.add(value.path, "Scan", len(value.entries))
            except Exception as exc:
                self.status.setText("Operation complete; could not save history: " + str(exc))

        def handle_drop(self, paths):
            if self.batch_page.busy:
                self.status.setText("Finish or cancel the current batch before adding images.")
                return
            if len(paths) == 1 and Path(paths[0]).is_file():
                if self.stack.currentIndex() == 0:
                    self.pages[0].select_file(paths[0])
                else:
                    self.inspect_output(Path(paths[0]))
            else:
                self.switch(3)
                self.batch_page.load_paths(paths, auto_scan=True)

        def dragEnterEvent(self, event):
            urls = event.mimeData().urls()
            if urls and all(url.isLocalFile() for url in urls):
                paths = [u.toLocalFile() for u in urls]
                self.drop_message.setText(f"Drop {len(paths)} images to analyze" if len(paths) > 1 else
                                          "Drop the folder to analyze" if Path(paths[0]).is_dir() else "Drop to analyze")
                self.overlay.setGeometry(self.sidebar.width() + 16, 76,
                                         self.width() - self.sidebar.width() - 32, self.height() - 124)
                self.overlay_fade.to(0.0, False)
                self.overlay.show()
                self.overlay.raise_()
                self.overlay_fade.to(1.0)
                event.acceptProposedAction()
            else:
                event.ignore()

        def dragMoveEvent(self, event):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dragLeaveEvent(self, event):
            self.overlay.hide()
            event.accept()

        def dropEvent(self, event):
            self.overlay.hide()
            urls = event.mimeData().urls()
            if urls and all(url.isLocalFile() for url in urls):
                event.acceptProposedAction()
                self.handle_drop([u.toLocalFile() for u in urls])

        def compare_paths(self, before, after):
            self.switch(2)
            page = self.compare_page
            if page.busy:
                return
            page.busy = True
            page.choose.setEnabled(False)
            def done(pair):
                page.busy = False
                page.choose.setEnabled(True)
                page.render(*pair)
            def fail(error):
                page.busy = False
                page.choose.setEnabled(True)
                QMessageBox.warning(self, "Comparison", error)
            self.run_job(lambda: (scan_image(before), scan_image(after)), done, fail)

        def open_comparison(self, result):
            self.compare_page.set_result(result)
            self.switch(2)

        def inspect_output(self, path: Path):
            if self.pages[1].busy:
                QMessageBox.information(self, "Scan in progress", "Wait for the current scan to finish.")
                return
            self.switch(1)
            self.pages[1].select_file(str(path))
            self.pages[1].start_scan()

        def run_job(self, function, success, failure, progress=None):
            job = Job(function, self)
            if progress is not None:
                job.function = lambda: function(job.progress.emit)
                job.progress.connect(progress)
            self.jobs.append(job)
            job.result.connect(success)
            job.failed.connect(failure)
            def finish():
                self.jobs.remove(job)
                job.deleteLater()
            job.finished.connect(finish)
            job.start()

        def closeEvent(self, event):
            if any(job.isRunning() for job in self.jobs):
                QMessageBox.information(self, "Operation in progress", "Wait for the operation to finish before closing.")
                event.ignore()
            else:
                event.accept()

    return Window()
