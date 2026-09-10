# -*- coding: utf-8 -*-
"""Unit tests for DiffView's incremental per-file diff accumulation."""

from qgitc.diffutils import DiffType, FileInfo, FileState
from qgitc.diffview import DiffView
from tests.base import TestBase


class TestDiffViewChunkedDiff(TestBase):
    """A file's diff spans several parse() chunks (QProcess delivers stdout
    in multiple readyRead chunks); the view must accumulate it across
    __onDiffAvailable calls instead of dropping continuation lines."""

    def doCreateRepo(self):
        """No repo needed for these unit-level tests."""
        pass

    def setUp(self):
        super().setUp()
        self._view = DiffView()

    def tearDown(self):
        self._view.deleteLater()
        self.processEvents()
        super().tearDown()

    def _emitChunk(self, lineItems, fileItems):
        self._view._DiffView__onDiffAvailable(lineItems, fileItems)

    def testFileDiffSpanningChunks(self):
        """Continuation chunks (no DiffType.File marker) must not be dropped."""
        # Chunk 1: the file marker, its info line and the first hunk lines.
        self._emitChunk(
            [(DiffType.File, b"include/shell/et.h"),
             (DiffType.FileInfo, b"index 9122d00ef..da719d5f5 100644"),
             (DiffType.Diff, b"@@ -2122,6 +2122,39 @@ struct ShellEtFindOptions"),
             (DiffType.Diff, b"+struct ShellEtFindResult")],
            {"include/shell/et.h": FileInfo(3)})

        # Chunk 2: continuation of the same file's diff — no file marker.
        self._emitChunk(
            [(DiffType.Diff, b"+{"),
             (DiffType.Diff, b"+       std::u16string searchText;"),
             (DiffType.Diff, b"+};")],
            {})

        self._view._flushSplitFile()

        self.assertIn("include/shell/et.h", self._view._pendingDiffs)
        lineItems, _ = self._view._pendingDiffs["include/shell/et.h"]
        # marker + info + hunk header + 4 content lines = 7
        self.assertEqual(7, len(lineItems),
                         "all lines from both chunks must be kept")

    def testNextFileMarkerFlushesPrevious(self):
        """A new file marker must flush the accumulated previous file."""
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.Diff, b"+first")],
            {"a.txt": FileInfo(1)})

        self._emitChunk(
            [(DiffType.Diff, b"+second"),
             (DiffType.File, b"b.txt"),
             (DiffType.Diff, b"+other")],
            {"b.txt": FileInfo(3)})

        self.assertIn("a.txt", self._view._pendingDiffs)
        lineItems, _ = self._view._pendingDiffs["a.txt"]
        self.assertEqual(3, len(lineItems),
                         "a.txt must carry its marker line and both diff lines")
        self.assertEqual([b"+first", b"+second"],
                         [d for t, d in lineItems if t == DiffType.Diff])

        # b.txt is still being split (no following marker yet)
        self.assertNotIn("b.txt", self._view._pendingDiffs)
        self.assertEqual("b.txt", self._view._splitFile)

    def testStateUpdateAppliedToPendingFile(self):
        """fileStateChanged for the file being split must update its
        pending FileInfo (the file is not in the list until the flush)."""
        info = FileInfo(1)
        self._emitChunk(
            [(DiffType.File, b"new.txt"),
             (DiffType.Diff, b"+content")],
            {"new.txt": info})

        self._view._DiffView__onDiffFileStateChanged("new.txt", FileState.Added)

        self.assertEqual(FileState.Added, info.state)

    def testClearResetsSplitState(self):
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.Diff, b"+x")],
            {"a.txt": FileInfo(1)})

        self._view.clear()

        self.assertIsNone(self._view._splitFile)
        self.assertIsNone(self._view._splitInfo)
        self.assertEqual([], self._view._splitLines)
        self.assertEqual({}, self._view._pendingDiffs)
