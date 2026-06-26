# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, PropertyMock, patch

from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorystore import AiChatHistoryStore
from qgitc.settings import Settings
from tests.base import TestBase


class TestAiChatHistoryStoreEmptyHistories(TestBase):
    """Tests for the empty-history filtering behavior in AiChatHistoryStore.

    Verifies that empty conversations (histories with no messages) are:
    - Skipped when loading from settings (ensureLoaded)
    - Not persisted when updating modelId (updateCurrentModelId)
    - Not persisted when updating from messages (updateFromMessages)
    """

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self._settings = self.app.settings()
        self._store = AiChatHistoryStore(self._settings)

    # ------------------------------------------------------------------
    # ensureLoaded: empty histories from settings should be skipped
    # ------------------------------------------------------------------
    def test_ensureLoaded_skips_empty_histories(self):
        """ensureLoaded should skip histories with no messages when loading from settings."""
        # Arrange: settings returns a mix of empty and non-empty histories
        nonEmptyHistory = AiChatHistory(
            title="Has Messages",
            messages=[{"role": "user", "content": "hello"}],
        )
        emptyHistory = AiChatHistory(
            title="Empty Conversation",
            messages=[],
        )

        with patch.object(
            self._settings,
            'chatHistories',
            return_value=[nonEmptyHistory.toDict(), emptyHistory.toDict()],
        ):
            self._store.ensureLoaded()

        loaded = self._store.model().histories()
        self.assertEqual(1, len(loaded))
        self.assertEqual(loaded[0].historyId, nonEmptyHistory.historyId)
        self.assertNotIn(emptyHistory.historyId, [h.historyId for h in loaded])

    def test_ensureLoaded_skips_all_empty_histories(self):
        """ensureLoaded should result in empty model when all persisted histories are empty."""
        empty1 = AiChatHistory(messages=[])
        empty2 = AiChatHistory(messages=[])

        with patch.object(
            self._settings,
            'chatHistories',
            return_value=[empty1.toDict(), empty2.toDict()],
        ):
            self._store.ensureLoaded()

        loaded = self._store.model().histories()
        self.assertEqual(0, len(loaded))

    def test_ensureLoaded_keeps_non_empty_histories(self):
        """ensureLoaded should keep all non-empty histories."""
        h1 = AiChatHistory(messages=[{"role": "user", "content": "a"}])
        h2 = AiChatHistory(messages=[{"role": "user", "content": "b"}])

        with patch.object(
            self._settings,
            'chatHistories',
            return_value=[h1.toDict(), h2.toDict()],
        ):
            self._store.ensureLoaded()

        loaded = self._store.model().histories()
        self.assertEqual(2, len(loaded))

    # ------------------------------------------------------------------
    # updateCurrentModelId: should not persist empty histories
    # ------------------------------------------------------------------
    def test_updateCurrentModelId_does_not_persist_empty_history(self):
        """updateCurrentModelId should NOT schedule a save for empty histories."""
        history = AiChatHistory(messages=[])
        self._store.model().insertHistory(0, history)

        with patch.object(self._store, '_scheduleSave') as mockSave:
            self._store.updateCurrentModelId(history.historyId, "new-model")

        mockSave.assert_not_called()

    def test_updateCurrentModelId_persists_non_empty_history(self):
        """updateCurrentModelId SHOULD schedule a save for histories with messages."""
        history = AiChatHistory(
            messages=[{"role": "user", "content": "hello"}],
            modelId="old-model",
        )
        self._store.model().insertHistory(0, history)

        with patch.object(self._store, '_scheduleSave') as mockSave:
            self._store.updateCurrentModelId(history.historyId, "new-model")

        mockSave.assert_called_once()

    def test_updateCurrentModelId_persists_when_modelId_unchanged(self):
        """updateCurrentModelId should NOT save when modelId hasn't changed."""
        history = AiChatHistory(
            messages=[{"role": "user", "content": "hello"}],
            modelId="same-model",
        )
        self._store.model().insertHistory(0, history)

        with patch.object(self._store, '_scheduleSave') as mockSave:
            self._store.updateCurrentModelId(history.historyId, "same-model")

        mockSave.assert_not_called()

    # ------------------------------------------------------------------
    # updateFromMessages: should not persist empty histories
    # ------------------------------------------------------------------
    def test_updateFromMessages_does_not_persist_when_messages_empty(self):
        """updateFromMessages should NOT schedule a save when the resulting messages list is empty."""
        history = AiChatHistory(messages=[])
        self._store.model().insertHistory(0, history)

        with patch.object(self._store, '_scheduleSave') as mockSave:
            self._store.updateFromMessages(history.historyId, [])

        mockSave.assert_not_called()

    def test_updateFromMessages_persists_when_messages_present(self):
        """updateFromMessages SHOULD schedule a save when messages are provided."""
        history = AiChatHistory(messages=[])
        self._store.model().insertHistory(0, history)

        with patch.object(self._store, '_scheduleSave') as mockSave, \
             patch('qgitc.agent.message_convert.messagesToHistoryDicts',
                   return_value=[{"role": "user", "content": "hello"}]):
            self._store.updateFromMessages(
                history.historyId,
                [{"role": "user", "content": "hello"}],
            )

        mockSave.assert_called_once()

    # ------------------------------------------------------------------
    # insertHistoryAtTop: should always insert (no filtering)
    # ------------------------------------------------------------------
    def test_insertHistoryAtTop_inserts_empty_history(self):
        """insertHistoryAtTop should insert empty histories (they are transient UI state)."""
        history = AiChatHistory(messages=[])
        self._store.insertHistoryAtTop(history)

        loaded = self._store.model().histories()
        self.assertEqual(1, len(loaded))
        self.assertEqual(loaded[0].historyId, history.historyId)

    def test_insertHistoryAtTop_inserts_non_empty_history(self):
        """insertHistoryAtTop should insert non-empty histories."""
        history = AiChatHistory(messages=[{"role": "user", "content": "hi"}])
        self._store.insertHistoryAtTop(history)

        loaded = self._store.model().histories()
        self.assertEqual(1, len(loaded))
        self.assertEqual(loaded[0].historyId, history.historyId)


if __name__ == "__main__":
    import unittest
    unittest.main()
