# -*- coding: utf-8 -*-
from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.gitutils import GitProcess
from tests.base import TestBase


class TestFindSubmoduleThread(TestBase):

    def createSubRepo(self):
        return True

    def testStartFailureFallsBackToFileWalk(self):
        """A failed process start must not hang the thread forever.

        QProcess emits errorOccurred (never finished) when the program
        cannot be started; without quitting the wait on it, the thread
        blocks until interrupted and submodules are never discovered
        (e.g. broken git binary).
        """
        oldBin = GitProcess.GIT_BIN
        GitProcess.GIT_BIN = "definitely-not-a-git-binary.exe"
        try:
            thread = FindSubmoduleThread(self.gitDir.name)
            thread.start()
            self.wait(5000, thread.isRunning)
        finally:
            GitProcess.GIT_BIN = oldBin

        self.assertFalse(thread.isRunning())
        self.assertIn("subRepo", thread.submodules)

    def testEventLoopNotRetainedAfterRun(self):
        """run() must not leave the QEventLoop referenced after it returns.

        The loop is created in the worker thread; keeping it as an instance
        attribute would destroy it later from the GUI thread (or at
        interpreter teardown) — cross-thread QObject destruction.
        """
        thread = FindSubmoduleThread(self.gitDir.name)
        thread.start()
        self.wait(5000, thread.isRunning)

        self.assertFalse(thread.isRunning())
        self.assertIsNone(thread._eventLoop)
        self.assertTrue(thread.submodules)
