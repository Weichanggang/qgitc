# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QWidget,
    QApplication)
from PySide2.QtGui import (
    QPainter,
    QFontMetrics,
    QTextCharFormat,
    QTextOption,
    QBrush,
    QColor)
from PySide2.QtCore import (
    Qt,
    QRect,
    QRectF,
    QPoint,
    QPointF,
    Signal,
    QElapsedTimer)

from .textline import (
    TextLine,
    SourceTextLineBase,
    createFormatRange)
from .colorschema import ColorSchema
from .stylehelper import dpiScaled
from .textcursor import TextCursor


__all__ = ["SourceViewer", "SourcePanel"]


class SourceTextLine(SourceTextLineBase):

    def __init__(self, text, font, option):
        super().__init__(TextLine.Source, text,
                         font, option)

    def rehighlight(self):
        formats = self._commonHighlightFormats()
        if formats:
            self._layout.setAdditionalFormats(formats)


class SourcePanel(QWidget):

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self._viewer = viewer

    def requestWidth(self, lineCount):
        return 0


class SourceViewer(QAbstractScrollArea):

    textLineClicked = Signal(TextLine)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []

        settings = qApp.settings()

        self._font = settings.diffViewFont()

        self._option = QTextOption()
        self._option.setWrapMode(QTextOption.NoWrap)

        fm = QFontMetrics(self._font)
        tabstopWidth = fm.width(' ') * settings.tabSize()
        self._option.setTabStop(tabstopWidth)

        if settings.showWhitespace():
            flags = self._option.flags()
            self._option.setFlags(flags | QTextOption.ShowTabsAndSpaces)

        self._lineHeight = fm.height()
        self._maxWidth = 0
        self._highlightLines = []

        self._panel = None
        self._onePixel = dpiScaled(1)

        self._cursor = TextCursor()
        self._clickTimer = QElapsedTimer()

        self.verticalScrollBar().valueChanged.connect(
            self._onVScrollBarValueChanged)

    def appendLine(self, line):
        textLine = SourceTextLine(line, self._font, self._option)
        textLine.setLineNo(len(self._lines))
        self._lines.append(textLine)
        self._maxWidth = max(self._maxWidth,
                             textLine.boundingRect().width())

        self._updatePanelGeo()
        self._adjustScrollbars()
        self.viewport().update()

    def clear(self):
        self._lines.clear()
        self._maxWidth = 0
        self._highlightLines.clear()
        self.viewport().update()

    def hasTextLines(self):
        return self.textLineCount() > 0

    def textLineCount(self):
        return len(self._lines)

    def textLineAt(self, n):
        return self._lines[n]

    def firstVisibleLine(self):
        return self.verticalScrollBar().value()

    @property
    def currentLineNo(self):
        return self.firstVisibleLine()

    def gotoLine(self, lineNo):
        if lineNo < 0 or lineNo >= self.textLineCount():
            return

        vScrollBar = self.verticalScrollBar()
        if vScrollBar.value() != lineNo:
            vScrollBar.setValue(lineNo)
            self.viewport().update()

    def contentOffset(self):
        if not self.hasTextLines():
            return QPointF(0, 0)

        x = self.horizontalScrollBar().value()

        return QPointF(-x, -0)

    def mapToContents(self, pos):
        x = pos.x() + self.horizontalScrollBar().value()
        y = pos.y() + 0
        return QPoint(x, y)

    def setPanel(self, panel):
        self._panel = panel
        if panel:
            self._updatePanelGeo()
        else:
            self.setViewportMargins(0, 0, 0, 0)

    @property
    def lineHeight(self):
        return self._lineHeight

    def textLineForPos(self, pos):
        if not self.hasTextLines():
            return None

        n = int(pos.y() / self.lineHeight)
        n += self.firstVisibleLine()

        if n >= self.textLineCount():
            n = self.textLineCount() - 1

        return self._lines[n]

    def highlightLines(self, lines):
        self._highlightLines = lines

        self.viewport().update()

    def selectAll(self):
        if not self.hasTextLines():
            return

        self._cursor.moveTo(0, 0)
        lastLine = self.textLineCount() - 1
        self._cursor.selectTo(lastLine, len(self.textLineAt(lastLine).text()))
        self._invalidateSelection()

    def _linesPerPage(self):
        return int(self.viewport().height() / self._lineHeight)

    def _adjustScrollbars(self):
        vScrollBar = self.verticalScrollBar()
        hScrollBar = self.horizontalScrollBar()
        if not self.hasTextLines():
            vScrollBar.setRange(0, 0)
            hScrollBar.setRange(0, 0)
            return

        hScrollBar.setRange(0, self._maxWidth - self.viewport().width())
        hScrollBar.setPageStep(self.viewport().width())

        linesPerPage = self._linesPerPage()
        totalLines = self.textLineCount()

        vScrollBar.setRange(0, totalLines - linesPerPage)
        vScrollBar.setPageStep(linesPerPage)

    def _onVScrollBarValueChanged(self, value):
        if self._panel:
            self._panel.update()

    def _updatePanelGeo(self):
        if self._panel:
            rc = self.rect()
            width = self._panel.requestWidth(self.textLineCount())
            self.setViewportMargins(width + self._onePixel, 0, 0, 0)
            self._panel.setGeometry(rc.left() + self._onePixel,
                                    rc.top() + self._onePixel,
                                    width,
                                    self.viewport().height())

    def _invalidateSelection(self):
        if not self._cursor.hasSelection():
            return

        begin = self._cursor.beginLine()
        end = self._cursor.endLine()

        x = 0
        y = (begin - self.firstVisibleLine()) * self.lineHeight
        w = self.viewport().width()
        h = (end - begin + 1) * self.lineHeight

        rect = QRect(x, y, w, h)
        # offset for some odd fonts LoL
        offset = int(self.lineHeight / 2)
        rect.adjust(0, -offset, 0, offset)
        self.viewport().update(rect)

    def _selectionFormatRange(self, lineIndex):
        if not self._cursor.within(lineIndex):
            return None

        textLine = self.textLineAt(lineIndex)
        start = 0
        end = len(textLine.text())

        if self._cursor.beginLine() == lineIndex:
            start = self._cursor.beginPos()
        if self._cursor.endLine() == lineIndex:
            end = self._cursor.endPos()

        fmt = QTextCharFormat()
        if self.hasFocus():
            fmt.setBackground(QBrush(ColorSchema.SelFocus))
        else:
            fmt.setBackground(QBrush(ColorSchema.SelNoFocus))

        return createFormatRange(start, end - start, fmt)

    def _isLetter(self, char):
            if char >= 'a' and char <= 'z':
                return True
            if char >= 'A' and char <= 'Z':
                return True

            if char == '_':
                return True

            if char.isdigit():
                return True

            return False

    def paintEvent(self, event):
        if not self._lines:
            return

        painter = QPainter(self.viewport())

        startLine = self.firstVisibleLine()
        endLine = startLine + self._linesPerPage() + 1
        endLine = min(self.textLineCount(), endLine)

        offset = self.contentOffset()
        viewportRect = self.viewport().rect()
        eventRect = event.rect()

        painter.setClipRect(eventRect)

        for i in range(startLine, endLine):
            textLine = self._lines[i]

            br = textLine.boundingRect()
            r = br.translated(offset)

            if i in self._highlightLines:
                fr = QRectF(br)
                fr.moveTop(fr.top() + r.top())
                fr.setLeft(0)
                fr.setRight(viewportRect.width() - offset.x())
                painter.fillRect(fr, QColor(192, 237, 197))

            formats = []

            # selection
            selectionRg = self._selectionFormatRange(i)
            if selectionRg:
                formats.append(selectionRg)

            textLine.draw(painter, offset, formats, QRectF(eventRect))

            offset.setY(offset.y() + r.height())

            if (offset.y() > viewportRect.height()):
                break

    def resizeEvent(self, event):
        if event.oldSize().height() != event.size().height():
            self._updatePanelGeo()
        self._adjustScrollbars()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        self._invalidateSelection()

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        tripleClick = False
        if self._clickTimer.isValid():
            tripleClick = not self._clickTimer.hasExpired(
                QApplication.doubleClickInterval())
            self._clickTimer.invalidate()

        if tripleClick:
            self._cursor.moveTo(textLine.lineNo(), 0)
            self._cursor.selectTo(textLine.lineNo(), len(textLine.text()))
            self._invalidateSelection()
        else:
            offset = textLine.offsetForPos(self.mapToContents(event.pos()))
            self._cursor.moveTo(textLine.lineNo(), offset)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines() or \
            self._cursor.hasSelection():
            return

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        self.textLineClicked.emit(textLine)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        self._clickTimer.restart()
        self._invalidateSelection()
        self._cursor.clear()

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        offset = textLine.offsetForPos(self.mapToContents(event.pos()))
        begin = offset
        end = offset

        # find the word
        content = textLine.text()
        if offset < len(content) and self._isLetter(content[offset]):
            for i in range(offset - 1, -1, -1):
                if self._isLetter(content[i]):
                    begin = i
                    continue
                break

            for i in range(offset + 1, len(content)):
                if self._isLetter(content[i]):
                    end = i
                    continue
                break

        end += 1
        word = content[begin:end]
        if word:
            self._cursor.moveTo(textLine.lineNo(), begin)
            self._cursor.selectTo(textLine.lineNo(), end)
            self._invalidateSelection()

    def mouseMoveEvent(self, event):
        if self._clickTimer.isValid():
            self._clickTimer.invalidate()

        if not self.hasTextLines():
            return

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        self._invalidateSelection()

        n = textLine.lineNo()
        offset = textLine.offsetForPos(self.mapToContents(event.pos()))
        self._cursor.selectTo(n, offset)

        self._invalidateSelection()
