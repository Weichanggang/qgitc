# -*- coding: utf-8 -*-
import sys
import time
import unittest
from unittest.mock import patch

from PySide6.QtTest import QSignalSpy

from qgitc.cancelevent import CancelEvent
from qgitc.submoduleexecutor import SubmoduleExecutor
from tests.base import TestBase


class Dummy:
    def dummyAction(self, submodule, data, cancelEvent: CancelEvent):
        return 1

    def dummyAction2(self, submodule, data, cancelEvent: CancelEvent):
        return "Hello", "World"

    def dummyResult(self, *kargs):
        pass


def _dummyAction(submodule, data, cancelEvent: CancelEvent):
    return submodule, "Hello, World!"


class TestSubmoduleExecutor(TestBase):
    def doCreateRepo(self):
        pass

    def testSubmit(self):
        dummy = Dummy()
        with patch.object(Dummy, "dummyAction", wraps=dummy.dummyAction) as mock:
            executor = SubmoduleExecutor()
            spy = QSignalSpy(executor.finished)
            spyStarted = QSignalSpy(executor.started)
            executor.submit(None, dummy.dummyAction)
            self.wait(10000, lambda: spyStarted.count() == 0)
            self.wait(10000, lambda: spy.count() == 0)
            mock.assert_called_once()
            self.assertIsNone(mock.call_args[0][0])
            self.assertIsNone(mock.call_args[0][1])
            self.assertIsInstance(mock.call_args[0][2], CancelEvent)
            executor.cancel(True)

    def testSumbit2(self):
        dummy = Dummy()
        with patch.object(Dummy, "dummyResult", wraps=dummy.dummyResult) as mock:
            executor = SubmoduleExecutor()
            spy = QSignalSpy(executor.finished)
            spyStarted = QSignalSpy(executor.started)
            executor.submit([None], dummy.dummyAction2, dummy.dummyResult)
            self.wait(10000, lambda: spyStarted.count() == 0)

            self.wait(10000, lambda: spy.count() == 0)
            mock.assert_called_once_with("Hello", "World")
            executor.cancel(True)
        self.processEvents()

    def _cancelAction(self, submodule, data, cancelEvent: CancelEvent):
        time.sleep(0.1)
        if cancelEvent.isSet():
            return True
        return False

    def testCancel(self):
        executor = SubmoduleExecutor()

        dummy = Dummy()
        with patch.object(Dummy, "dummyResult", wraps=dummy.dummyResult) as mock:
            spy = QSignalSpy(executor.finished)
            spyStarted = QSignalSpy(executor.started)
            executor.submit(None, self._cancelAction, dummy.dummyResult)
            self.wait(1000, lambda: spyStarted.count() == 0)
            self.wait(50, executor.isRunning)
            self.assertTrue(executor.isRunning())
            executor.cancel()
            self.assertFalse(executor.isRunning())
            # the signal is disconnected
            self.assertFalse(spy.wait(200))
            mock.assert_not_called()

        executor.cancel(True)
        self.assertEqual(0, len(executor._threads))
        self.processEvents()

    def testFailCancel(self):
        executor = SubmoduleExecutor()

        dummy = Dummy()
        with patch.object(Dummy, "dummyResult", wraps=dummy.dummyResult) as mock:
            spyStarted = QSignalSpy(executor.started)
            executor.submit(None, self._cancelAction, dummy.dummyResult)
            self.wait(1000, lambda: spyStarted.count() == 0)
            self.wait(150, executor.isRunning)
            self.assertFalse(executor.isRunning())
            executor.cancel()
            mock.assert_called_once()
            executor.cancel(True)

        self.processEvents()

    def _blockAction(self, submodule, data, cancelEvent: CancelEvent):
        time.sleep(4)

    @unittest.skipIf(sys.version_info >= (3, 14), "Skip on Python >= 3.14")
    def testAbort(self):
        executor = SubmoduleExecutor()

        with patch("logging.Logger.warning") as warning:
            spyStarted = QSignalSpy(executor.started)
            executor.submit(None, self._blockAction)
            self.wait(1000, lambda: spyStarted.count() == 0)
            self.assertTrue(executor.isRunning())
            executor.cancel(True)

            self.wait(100)
            self.assertFalse(executor.isRunning())

            self.assertEqual(warning.call_count, 2)
            warning.assert_any_call(
                "Thread did not stop within %d ms; orphaning for async cleanup",
                3000)
            warning.assert_any_call(
                "Submodule thread orphaned for async cleanup (%s)",
                "_blockAction")

        with patch("logging.Logger.warning") as warning:
            spyStarted = QSignalSpy(executor.started)
            executor.submit(None, self._blockAction)
            self.wait(1000, lambda: spyStarted.count() == 0)
            self.assertTrue(executor.isRunning())
            executor.cancel()

            # Actually running in background
            self.assertFalse(executor.isRunning())
            self.assertIsNone(executor._thread)

            warning.assert_not_called()

            self.assertEqual(1, len(executor._threads))

        executor.cancel(True)
        self.assertEqual(0, len(executor._threads))
        self.processEvents()

    def testMultiThreading(self):
        executor = SubmoduleExecutor()
        dummy = Dummy()
        with patch.object(Dummy, "dummyResult", wraps=dummy.dummyResult) as mock:
            spyStarted = QSignalSpy(executor.started)
            executor.submit([None, None], _dummyAction, dummy.dummyResult, True)
            self.wait(1000, lambda: spyStarted.count() == 0)
            self.wait(1000, executor.isRunning)
            mock.assert_any_call(None, "Hello, World!")

    def testMultiProcess(self):
        executor = SubmoduleExecutor()
        dummy = Dummy()
        with patch.object(Dummy, "dummyResult", wraps=dummy.dummyResult) as mock:
            spyStarted = QSignalSpy(executor.started)
            executor.submit(None, _dummyAction, dummy.dummyResult, False)
            # wait for thread to start
            self.wait(1000, lambda: spyStarted.count() == 0)
            self.wait(3000, executor.isRunning)
            # wait for result
            self.wait(100)
            mock.assert_any_call(None, "Hello, World!")


class TestSubmoduleExecutorCancelReentrancy(TestBase):
    """Regression tests for cancel()'s re-entrancy holes.

    _terminateThread() pumps the GUI event loop while waiting for the
    thread, so queued finished() handlers run re-entrantly — and
    StatusFetcher.onFinished() re-submits, mutating _thread/_threads
    underneath a running cancel(). The disconnects must therefore be
    idempotent and the bookkeeping must not leave stale references.
    """

    def doCreateRepo(self):
        pass

    def testCancelToleratesAlreadyDisconnectedThread(self):
        """cancel(force=True) must not raise when the thread's finished()
        connection was already disconnected by a previous cancel pass."""
        executor = SubmoduleExecutor()
        executor.submit(["."], lambda *a: None)
        thread = executor._thread

        # simulate a previous cancel pass that already disconnected
        # _onThreadFinished (e.g. via its force-cleanup loop)
        thread.finished.disconnect(executor._onThreadFinished)

        # must not raise
        executor.cancel(True)

        self.assertIsNone(executor._thread)
        self.assertEqual(executor._threads, [])
        self.processEvents()

    def testCancelClearsStaleThreadReference(self):
        """cancel(force=True) must clear _thread even when the thread
        already finished but its queued finished() handlers (which clear
        _thread) have not been delivered yet."""
        executor = SubmoduleExecutor()
        executor.submit(["."], lambda *a: None)
        thread = executor._thread

        # wait for the thread to finish WITHOUT pumping events, so the
        # queued finished() handlers stay pending
        thread.wait(5000)
        self.assertFalse(thread.isRunning())
        self.assertIsNotNone(executor._thread)

        executor.cancel(True)

        self.assertIsNone(executor._thread)
        self.assertEqual(executor._threads, [])
        self.processEvents()

    def testCancelForceKeepsThreadSubmittedDuringTerminate(self):
        """A thread submitted re-entrantly during cancel()'s terminate wait
        must survive in _threads instead of being disconnected and cleared
        by the same cancel pass."""
        executor = SubmoduleExecutor()

        def action(submodule, userData, cancelEvent):
            # mimics StatusFetcher.onFinished re-fetching while
            # _terminateThread pumps the event loop
            executor.submit(["."], lambda *a: None)

        executor.submit(["."], action)
        executor.cancel(True)
        self.processEvents()

        # the re-entrantly submitted thread must still be tracked with its
        # finished() connection intact (not disconnected behind our back)
        for thread in executor._threads:
            self.assertTrue(thread.isRunning() or thread.isFinished())

        executor.cancel(True)
        self.assertEqual(executor._threads, [])
        self.processEvents()
