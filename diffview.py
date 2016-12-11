# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from collections import namedtuple

from common import *

import subprocess
import re


# item type for LineItem
ItemInvalid = -1
ItemAuthor = 0
ItemParent = 1
ItemBranch = 2
ItemComments = 3
ItemFile = 4
ItemFileInfo = 5
ItemDiff = 6

# diff line content
LineItem = namedtuple("LineItem", ["type", "content"])

diff_re = re.compile(b"^diff --(git a/(.*) b/(.*)|cc (.*))")
diff_begin_re = re.compile("^@{2,}( (\+|\-)[0-9]+,[0-9]+)+ @{2,}")
diff_begin_bre = re.compile(b"^@{2,}( (\+|\-)[0-9]+,[0-9]+)+ @{2,}")

diff_encoding = "utf-8"


class TreeItemDelegate(QItemDelegate):

    def __init__(self, parent=None):
        super(TreeItemDelegate, self).__init__(parent)
        self.pattern = None

    def paint(self, painter, option, index):
        text = index.data()

        itemSelected = option.state & QStyle.State_Selected
        self.drawBackground(painter, option, index)
        self.drawFocus(painter, option, option.rect)

        textLayout = QTextLayout(text, option.font)
        textOption = QTextOption()
        textOption.setWrapMode(QTextOption.NoWrap)

        textLayout.setTextOption(textOption)

        formats = []
        if index.row() != 0 and self.pattern:
            matchs = self.pattern.finditer(text)
            fmt = QTextCharFormat()
            if itemSelected:
                fmt.setForeground(QBrush(Qt.yellow))
            else:
                fmt.setBackground(QBrush(Qt.yellow))
            for m in matchs:
                rg = QTextLayout.FormatRange()
                rg.start = m.start()
                rg.length = m.end() - rg.start
                rg.format = fmt
                formats.append(rg)

        textLayout.setAdditionalFormats(formats)

        textLayout.beginLayout()
        line = textLayout.createLine()
        line.setPosition(QPointF(0, 0))
        textLayout.endLayout()

        painter.save()
        if itemSelected:
            painter.setPen(option.palette.color(QPalette.HighlightedText))
        else:
            painter.setPen(option.palette.color(QPalette.WindowText))

        textLayout.draw(painter, QPointF(option.rect.topLeft()))
        painter.restore()

    def setHighlightPattern(self, pattern):
        self.pattern = pattern


class DiffView(QWidget):

    def __init__(self, parent=None):
        super(DiffView, self).__init__(parent)

        self.viewer = PatchViewer(self)
        self.treeWidget = QTreeWidget(self)
        self.filterPath = None
        self.twMenu = QMenu()
        self.commit = None

        self.twMenu.addAction(self.tr("External &diff"),
                              self.__onExternalDiff)
        self.twMenu.addAction(self.tr("&Copy path"),
                              self.__onCopyPath)

        splitter = QSplitter(self)
        splitter.addWidget(self.viewer)
        splitter.addWidget(self.treeWidget)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.treeWidget.setColumnCount(1)
        self.treeWidget.setHeaderHidden(True)
        self.treeWidget.setRootIsDecorated(False)
        self.treeWidget.header().setStretchLastSection(False)
        self.treeWidget.header().setResizeMode(QHeaderView.ResizeToContents)

        self.itemDelegate = TreeItemDelegate(self)
        self.treeWidget.setItemDelegate(self.itemDelegate)

        width = self.sizeHint().width()
        sizes = [width * 2 / 3, width * 1 / 3]
        splitter.setSizes(sizes)

        self.treeWidget.currentItemChanged.connect(self.__onTreeItemChanged)
        self.viewer.fileRowChanged.connect(self.__onFileRowChanged)

        self.treeWidget.installEventFilter(self)

    def __onTreeItemChanged(self, current, previous):
        if current:
            row = current.data(0, Qt.UserRole)
            self.viewer.scrollToRow(row)

    def __onFileRowChanged(self, row):
        for i in range(self.treeWidget.topLevelItemCount()):
            item = self.treeWidget.topLevelItem(i)
            n = item.data(0, Qt.UserRole)
            if n == row:
                self.treeWidget.blockSignals(True)
                self.treeWidget.setCurrentItem(item)
                self.treeWidget.blockSignals(False)
                break

    def __onExternalDiff(self):
        item = self.treeWidget.currentItem()
        if not item:
            return
        if not self.commit:
            return
        filePath = item.text(0)
        externalDiff(self.commit, filePath)

    def __onCopyPath(self):
        item = self.treeWidget.currentItem()
        if not item:
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(item.text(0))

    def __addToTreeWidget(self, string, row):
        """specify the @row number of the file in the viewer"""
        item = QTreeWidgetItem([string])
        item.setData(0, Qt.UserRole, row)
        self.treeWidget.addTopLevelItem(item)
        if row == 0:
            self.treeWidget.setCurrentItem(item)

    def __commitToLineItems(self, commit):
        items = []
        item = LineItem(ItemAuthor,
                        self.tr("Author: ") + commit.author +
                        " " + commit.authorDate)
        items.append(item)

        item = LineItem(ItemAuthor,
                        self.tr("Committer: ") + commit.commiter +
                        " " + commit.commiterDate)

        items.append(item)

        # TODO: get commit info
        for parent in commit.parents:
            item = LineItem(ItemParent, self.tr("Parent: ") + parent)
            items.append(item)

        # TODO: add child, branch etc...

        items.append(LineItem(ItemComments, ""))

        comments = commit.comments.split('\n')
        for comment in comments:
            content = comment if not comment else "    " + comment
            item = LineItem(ItemComments, content)
            items.append(item)

        items.append(LineItem(ItemComments, ""))

        return items

    # TODO: shall we cache the commit?
    def showCommit(self, commit):
        self.clear()
        self.commit = commit

        data = getCommitRawDiff(commit.sha1, self.filterPath)
        lines = data.split(b'\n')

        self.__addToTreeWidget(self.tr("Comments"), 0)

        lineItems = []
        lineItems.extend(self.__commitToLineItems(commit))

        isDiffContent = False
        lastEncoding = None

        for line in lines:
            match = diff_re.search(line)
            if match:
                fileA = None
                fileB = None
                if match.group(4):  # diff --cc
                    fileA = match.group(4).decode(diff_encoding)
                else:
                    fileA = match.group(2).decode(diff_encoding)
                    fileB = match.group(3).decode(diff_encoding)

                row = len(lineItems)
                self.__addToTreeWidget(fileA, row)
                # renames, keep new file name only
                if fileB and fileB != fileA:
                    lineItems.append(LineItem(ItemFile, fileB))
                    self.__addToTreeWidget(fileB, row)
                else:
                    lineItems.append(LineItem(ItemFile, fileA))

                isDiffContent = False

                continue

            itemType = ItemInvalid

            if isDiffContent:
                itemType = ItemDiff
            elif diff_begin_bre.search(line):
                isDiffContent = True
                itemType = ItemDiff
            elif line.startswith(b"--- ") or line.startswith(b"+++ "):
                continue
            elif not line:  # ignore the empty info line
                continue
            else:
                itemType = ItemFileInfo

            line, lastEncoding = decodeDiffData(line, lastEncoding)
            if itemType != ItemDiff:
                line = line.rstrip('\r')
            else:
                line = line.replace('\r', '^M')
            lineItems.append(LineItem(itemType, line))

        self.viewer.setData(lineItems)

    def clear(self):
        self.treeWidget.clear()
        self.viewer.setData(None)

    def setFilterPath(self, path):
        # no need update
        self.filterPath = path

    def updateSettings(self):
        self.viewer.resetFont()

    def highlightKeyword(self, pattern, field=FindField.Comments):
        self.viewer.highlightKeyword(pattern, field)
        if field == FindField.Paths:
            self.itemDelegate.setHighlightPattern(pattern)
        else:
            self.itemDelegate.setHighlightPattern(None)
        self.treeWidget.viewport().update()

    def eventFilter(self, obj, event):
        if obj != self.treeWidget:
            return False

        if event.type() != QEvent.ContextMenu:
            return False

        item = self.treeWidget.currentItem()
        if not item:
            return False

        if self.treeWidget.topLevelItemCount() < 2:
            return False

        if item == self.treeWidget.topLevelItem(0):
            return False

        self.twMenu.exec(event.globalPos())

        return False


class PatchViewer(QAbstractScrollArea):
    fileRowChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super(PatchViewer, self).__init__(parent)

        self.lineItems = []
        self.lineSpace = 5  # space between each line
        self.resetFont()

        self.showWhiteSpace = True
        self.highlightPattern = None
        self.highlightField = FindField.Comments

        # width of LineItem.content
        self.itemWidths = {}

        # FIXME: show scrollbar always to prevent dead loop
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.verticalScrollBar().valueChanged.connect(
            self.__onVScollBarValueChanged)

    def resetFont(self):
        # font for comments, file info, diff
        self.fonts = [None, None, None]

        settings = QApplication.instance().settings()
        fm = QFontMetrics(settings.diffViewFont())
        # total height of a line
        self.lineHeight = fm.height() + self.lineSpace

        self.tabstopWidth = fm.width(' ') * 4

        self.__adjust()

    def setData(self, items):
        self.lineItems = items
        self.itemWidths.clear()

        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()
        hScrollBar.blockSignals(True)
        vScrollBar.blockSignals(True)

        hScrollBar.setValue(0)
        vScrollBar.setValue(0)

        hScrollBar.blockSignals(False)
        vScrollBar.blockSignals(False)

        self.__adjust()
        self.viewport().update()

    def scrollToRow(self, row):
        vScrollBar = self.verticalScrollBar()
        if vScrollBar.value() != row:
            vScrollBar.blockSignals(True)
            vScrollBar.setValue(row)
            vScrollBar.blockSignals(False)
            self.__updateHScrollBar()
            self.viewport().update()

    def highlightKeyword(self, pattern, field):
        self.highlightPattern = pattern
        self.highlightField = field
        self.viewport().update()

    def mouseMoveEvent(self, event):
        pass

    def mousePressEvent(self, event):
        pass

    def resizeEvent(self, event):
        self.__adjust()

    def paintEvent(self, event):
        if not self.lineItems:
            return

        painter = QPainter(self.viewport())

        startLine = self.verticalScrollBar().value()
        endLine = startLine + self.__linesPerPage() + 1
        endLine = min(len(self.lineItems), endLine)

        offsetX = self.horizontalScrollBar().value()
        x = 0 - offsetX
        y = 0

        # TODO:  selection and many many...
        for i in range(startLine, endLine):
            item = self.lineItems[i]

            rect = QRect(x, y,
                         self.viewport().width() - x,
                         self.lineHeight)
            flags = Qt.AlignLeft | Qt.AlignVCenter

            if self.__drawComments(painter, item, rect, flags):
                pass
            elif self.__drawInfo(painter, item, rect, flags):
                pass
            elif self.__drawDiff(painter, item, rect, flags):
                pass
            else:
                painter.drawText(rect, flags, item.content)

            y += self.lineHeight

    def commentsFont(self):
        if not self.fonts[0]:
            settings = QApplication.instance().settings()
            self.fonts[0] = settings.diffViewFont()
        return self.fonts[0]

    def fileInfoFont(self):
        if not self.fonts[1]:
            settings = QApplication.instance().settings()
            self.fonts[1] = settings.diffViewFont()
            self.fonts[1].setBold(True)
        return self.fonts[1]

    def diffFont(self):
        if not self.fonts[2]:
            settings = QApplication.instance().settings()
            self.fonts[2] = settings.diffViewFont()
        return self.fonts[2]

    def itemFont(self, itemType):
        if itemType >= ItemAuthor and itemType <= ItemComments:
            return self.commentsFont()
        elif itemType >= ItemFile and itemType <= ItemFileInfo:
            return self.fileInfoFont()
        else:
            return self.diffFont()

    def __highlightFormatRange(self, text):
        formats = []
        if self.highlightPattern:
            matchs = self.highlightPattern.finditer(text)
            for m in matchs:
                rg = QTextLayout.FormatRange()
                rg.start = m.start()
                rg.length = m.end() - rg.start
                fmt = QTextCharFormat()
                fmt.setBackground(QBrush(Qt.yellow))
                rg.format = fmt
                formats.append(rg)
        return formats

    def __drawComments(self, painter, item, rect, flags):
        if not (item.type >= ItemAuthor and item.type <= ItemComments):
            return False

        painter.save()
        painter.setFont(self.commentsFont())

        textLayout = QTextLayout(item.content, self.commentsFont())

        textOption = QTextOption()
        textOption.setWrapMode(QTextOption.NoWrap)

        textLayout.setTextOption(textOption)

        if self.highlightField == FindField.Comments:
            formats = self.__highlightFormatRange(item.content)
            textLayout.setAdditionalFormats(formats)

        textLayout.beginLayout()
        line = textLayout.createLine()
        line.setPosition(QPointF(0, 0))
        textLayout.endLayout()

        textLayout.draw(painter, QPointF(rect.topLeft()))

        painter.restore()

        return True

    def __drawInfo(self, painter, item, rect, flags):
        if item.type != ItemFile and item.type != ItemFileInfo:
            return False

        painter.save()
        # first fill background
        painter.fillRect(rect, QBrush(QColor(170, 170, 170)))

        # now the text
        painter.setFont(self.fileInfoFont())
        painter.drawText(rect, flags, item.content)

        painter.restore()

        return True

    def __drawDiff(self, painter, item, rect, flags):
        if item.type != ItemDiff:
            return False

        painter.save()

        textOption = QTextOption()
        textOption.setTabStop(self.tabstopWidth)
        textOption.setWrapMode(QTextOption.NoWrap)
        if self.showWhiteSpace:
            textOption.setFlags(QTextOption.ShowTabsAndSpaces)

        textLayout = QTextLayout(item.content, self.diffFont())
        textLayout.setTextOption(textOption)

        formats = []

        if self.showWhiteSpace:
            # for the tab arrow
            formatRange = QTextLayout.FormatRange()
            formatRange.start = 0
            formatRange.length = len(textLayout.text())
            formats.append(formatRange)

        # format for \r
        if textLayout.text().endswith("^M"):
            fmtCRRg = QTextLayout.FormatRange()
            fmtCRRg.start = len(textLayout.text()) - 2
            fmtCRRg.length = 2
            fmt = QTextCharFormat()
            fmt.setForeground(QBrush(Qt.white))
            fmt.setBackground(QBrush(Qt.black))
            fmtCRRg.format = fmt
            formats.append(fmtCRRg)

        if self.highlightField == FindField.Diffs:
            formats.extend(self.__highlightFormatRange(item.content))
        textLayout.setAdditionalFormats(formats)

        textLayout.beginLayout()

        line = textLayout.createLine()

        textLayout.endLayout()

        pen = painter.pen()
        if diff_begin_re.search(item.content) or \
                item.content.startswith("\ No newline "):
            pen.setColor(QColor(0, 0, 255))
        elif item.content.lstrip().startswith("+"):
            pen.setColor(QColor(0, 168, 0))
        elif item.content.lstrip().startswith("-"):
            pen.setColor(QColor(255, 0, 0))

        painter.setPen(pen)
        textLayout.draw(painter, QPointF(rect.topLeft()))

        painter.restore()

        return True

    def __linesPerPage(self):
        return int(self.viewport().height() / self.lineHeight)

    def __totalLines(self):
        return len(self.lineItems)

    def __adjust(self):

        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()

        if not self.lineItems:
            hScrollBar.setRange(0, 0)
            vScrollBar.setRange(0, 0)
            return

        linesPerPage = self.__linesPerPage()
        totalLines = self.__totalLines()

        vScrollBar.setRange(0, totalLines - linesPerPage)
        vScrollBar.setPageStep(linesPerPage)

        self.__updateHScrollBar()

    def __updateHScrollBar(self):
        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()

        if not self.lineItems:
            hScrollBar.setRange(0, 0)
            return

        linesPerPage = self.__linesPerPage()
        totalLines = self.__totalLines()

        offsetY = vScrollBar.value()
        maxY = min(totalLines, offsetY + linesPerPage)

        maxWidth = 0
        for i in range(offsetY, maxY):
            if i in self.itemWidths:
                width = self.itemWidths[i]
            else:
                item = self.lineItems[i]
                fm = QFontMetrics(self.itemFont(item.type))
                width = fm.width(item.content)
                self.itemWidths[i] = width
            maxWidth = max(maxWidth, width)

        hScrollBar.setRange(0, maxWidth - self.viewport().width())
        hScrollBar.setPageStep(self.viewport().width())

    def __onVScollBarValueChanged(self, value):
        self.__updateHScrollBar()

        if not self.lineItems:
            return

        # TODO: improve
        for i in range(value, -1, -1):
            item = self.lineItems[i]
            if item.type == ItemFile:
                self.fileRowChanged.emit(i)
                break
            elif item.type == ItemParent or item.type == ItemAuthor:
                self.fileRowChanged.emit(0)
                break
