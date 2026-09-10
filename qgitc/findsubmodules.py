# -*- coding: utf-8 -*-

import os

from PySide6.QtCore import QEventLoop, QProcess, QThread
from shiboken6 import Shiboken

from qgitc.common import logger
from qgitc.gitutils import Git, GitProcess


class FindSubmoduleThread(QThread):
    BUILD_DIR_NAMES = {"build", "debug", "release"}

    def __init__(self, repoDir, parent=None):
        super(FindSubmoduleThread, self).__init__(parent)

        self.setRepoDir(repoDir)
        self._submodules = []
        self._eventLoop = None

    def setRepoDir(self, repoDir):
        self._repoDir = os.path.normcase(os.path.normpath(repoDir))

    @property
    def submodules(self):
        if self.isFinished() and not self.isInterruptionRequested():
            return self._submodules
        return []

    def _isIgnoredPath(self, relPath):
        if not relPath:
            return False

        relPath = relPath.replace("\\", "/")
        data = Git.checkOutput(["check-ignore", "--", relPath],
                               text=True, repoDir=self._repoDir)
        return bool(data and data.strip())

    def _isBuildDirPath(self, relPath):
        if not relPath:
            return False

        parts = [p.lower() for p in relPath.replace("\\", "/").split("/") if p]
        return any(
            part.startswith(name) or part.endswith(name)
            for part in parts
            for name in self.BUILD_DIR_NAMES
        )

    def _filterIgnoredSubdirs(self, root, subdirs):
        if not subdirs:
            return []

        relRoot = os.path.relpath(root, self._repoDir)
        if relRoot == ".":
            relRoot = ""

        filteredSubdirs = []
        for subdir in subdirs:
            relPath = subdir if not relRoot else os.path.join(relRoot, subdir)
            if self._isBuildDirPath(relPath) and self._isIgnoredPath(relPath):
                continue
            filteredSubdirs.append(subdir)
        return filteredSubdirs

    def run(self):
        self._submodules.clear()
        if self.isInterruptionRequested():
            return

        # try git submodule first
        self._eventLoop = QEventLoop()
        process = QProcess()
        process.setWorkingDirectory(self._repoDir)
        process.finished.connect(self._eventLoop.quit)
        # A failed start emits errorOccurred and never finished; without
        # quitting on it the wait below would block until interrupted and
        # submodules would never be discovered (e.g. broken git binary).
        process.errorOccurred.connect(self._eventLoop.quit)
        args = ["submodule", "foreach", "--quiet", "echo $name"]
        process.start(GitProcess.GIT_BIN, args)
        if process.state() != QProcess.ProcessState.NotRunning:
            # On Windows a failed start is reported synchronously from
            # start() (errorOccurred above), so only wait when it actually
            # started; a quit delivered before exec() may be lost.
            self._eventLoop.exec()
        # Drop the loop here so it is destroyed in this (worker) thread;
        # keeping it as an instance attribute would destroy it later from
        # the GUI thread or at interpreter teardown — cross-thread QObject
        # destruction.
        self._eventLoop = None

        if not Shiboken.isValid(process):
            # The interpreter is tearing down and already destroyed the
            # underlying C++ object; bail out without touching it.
            return

        if self.isInterruptionRequested():
            if process.state() == QProcess.ProcessState.Running:
                process.close()
                process.waitForFinished(50)
                if process.state() == QProcess.ProcessState.Running:
                    process.kill()
                    logger.warning("Kill find submodule process")
            return

        if process.exitCode() == 0:
            data = process.readAll().data()
            if data:
                self._submodules = data.decode("utf-8").rstrip().split('\n')
                self._submodules.insert(0, ".")
                return

        submodules = []
        # some projects may not use submodule or subtree
        max_level = 5 + self._repoDir.count(os.path.sep)
        for root, subdirs, files in os.walk(self._repoDir, topdown=True):
            if self.isInterruptionRequested():
                return
            isRepoRoot = os.path.normcase(root) == self._repoDir

            if not isRepoRoot and (".git" in subdirs or ".git" in files):
                directory = root.replace(self._repoDir + os.sep, "")
                if directory and Git.isRepoRoot(root):
                    submodules.append(directory)

            if root.count(os.path.sep) >= max_level or root.endswith(".git"):
                del subdirs[:]
            else:
                # ignore all '.dir'
                visibleSubdirs = [d for d in subdirs if not d.startswith(".")]
                subdirs[:] = self._filterIgnoredSubdirs(root, visibleSubdirs)

        if submodules:
            submodules.insert(0, '.')

        self._submodules = submodules

    def requestInterruption(self):
        super().requestInterruption()
        if self._eventLoop:
            self._eventLoop.quit()
