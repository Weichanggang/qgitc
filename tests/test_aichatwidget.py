# -*- coding: utf-8 -*-

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from qgitc.aichathistory import AiChatHistory
from qgitc.aichatwidget import AiChatWidget
from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiModelBase
from tests.base import TestBase


class TestActiveRequestModelId(TestBase):

    def doCreateRepo(self):
        pass  # No repo needed

    def _makeWidget(self) -> AiChatWidget:
        widget = AiChatWidget(parent=None, embedded=False, hideHistoryPanel=True)
        # Process any pending timers (e.g. _onDelayInit)
        self.processEvents()
        return widget

    # ------------------------------------------------------------------
    # Test 1: _saveChatHistoryFromLoop uses the snapshot, not model.modelId
    # ------------------------------------------------------------------
    def test_saveChatHistory_uses_activeRequestModelId(self):
        widget = self._makeWidget()

        # Arrange: fake agent loop with messages
        fakeLoop = MagicMock()
        fakeLoop.messages.return_value = [{"role": "user", "content": "hi"}]
        widget._agentLoop = fakeLoop

        # Arrange: fake history
        fakeHistory = MagicMock()
        fakeHistory.historyId = "hist-1"
        widget._historyPanel = MagicMock()
        widget._historyPanel.currentHistory.return_value = fakeHistory

        # Arrange: fake model with modelId = "model-B" (would be wrong if used)
        fakeModel = MagicMock()
        fakeModel.modelId = "model-B"
        fakeModel.name = "model-B"
        widget._contextPanel = MagicMock()
        widget._contextPanel.cbBots = MagicMock()
        widget._contextPanel.cbBots.currentData.return_value = fakeModel

        # Arrange: snapshot was captured at submit time
        widget._activeRequestModelId = "model-A"

        # Arrange: fake store
        fakeStore = MagicMock()
        fakeStore.updateFromMessages.return_value = fakeHistory
        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(
                 ApplicationBase.instance(),
                 'aiChatHistoryStore',
                 return_value=fakeStore,
             ):
            widget._saveChatHistoryFromLoop()

        _, kwargs = fakeStore.updateFromMessages.call_args
        self.assertEqual(kwargs.get("modelId"), "model-A")
        self.assertNotEqual(kwargs.get("modelId"), "model-B")

    # ------------------------------------------------------------------
    # Test 2: _onAgentFinished clears _activeRequestModelId after saving
    # ------------------------------------------------------------------
    def test_onAgentFinished_clears_activeRequestModelId(self):
        widget = self._makeWidget()
        widget._activeRequestModelId = "model-A"

        with patch.object(widget, '_saveChatHistoryFromLoop'), \
             patch.object(widget, '_updateStatus'), \
             patch.object(widget._chatBot, 'collapseLatestReasoningBlock'):
            widget._onAgentFinished()

        self.assertIsNone(widget._activeRequestModelId)

    # ------------------------------------------------------------------
    # Test 3: _resetAgentLoop clears _activeRequestModelId (stale snapshot)
    # ------------------------------------------------------------------
    def test_resetAgentLoop_clears_activeRequestModelId(self):
        widget = self._makeWidget()
        widget._activeRequestModelId = "model-A"

        # No live agent loop — _resetAgentLoop should still clear the snapshot
        widget._resetAgentLoop()

        self.assertIsNone(widget._activeRequestModelId)


class TestModelsReadyModelIdUpdate(TestBase):
    """Tests for _onModelsReady: modelId should only be updated for new (empty) conversations."""

    def doCreateRepo(self):
        pass  # No repo needed

    def _makeWidget(self) -> AiChatWidget:
        widget = AiChatWidget(parent=None, embedded=False, hideHistoryPanel=True)
        self.processEvents()
        return widget

    def test_modelsReady_does_not_update_modelId_for_loaded_history_with_messages(self):
        """Bug: modelsReady must NOT overwrite the modelId of a loaded history that has messages."""
        widget = self._makeWidget()

        # Use a real AiModelBase so modelsReady is a real Qt signal and sender() works.
        realModel = AiModelBase("http://test", model="bar-model")
        realModel.modelsReady.connect(widget._onModelsReady)

        # History with messages — this is a loaded/existing conversation.
        fakeHistory = MagicMock()
        fakeHistory.messages = [{"role": "user", "content": "hello"}]

        updateCalls = []
        with patch.object(widget, 'currentChatModel', return_value=realModel), \
             patch.object(widget._contextPanel, 'setupModelNames'), \
             patch.object(widget._historyPanel, 'currentHistory', return_value=fakeHistory), \
             patch.object(widget._historyPanel, 'updateCurrentModelId',
                          side_effect=lambda modelId: updateCalls.append(modelId)):
            realModel.modelsReady.emit()

        self.assertEqual(
            [], updateCalls,
            "updateCurrentModelId should NOT be called when the history already has messages",
        )

    def test_modelsReady_updates_modelId_for_empty_new_conversation(self):
        """modelsReady SHOULD update modelId when the current history is empty (new conversation)."""
        widget = self._makeWidget()

        realModel = AiModelBase("http://test", model="bar-model")
        realModel.modelsReady.connect(widget._onModelsReady)

        # Empty history — this is a brand-new conversation.
        fakeHistory = MagicMock()
        fakeHistory.messages = []

        updateCalls = []
        with patch.object(widget, 'currentChatModel', return_value=realModel), \
             patch.object(widget._contextPanel, 'setupModelNames'), \
             patch.object(widget._historyPanel, 'currentHistory', return_value=fakeHistory), \
             patch.object(widget._historyPanel, 'updateCurrentModelId',
                          side_effect=lambda modelId: updateCalls.append(modelId)):
            realModel.modelsReady.emit()

        self.assertEqual(
            1, len(updateCalls),
            "updateCurrentModelId should be called once for a new (empty) conversation",
        )

    def test_modelsReady_updates_modelId_when_no_history_exists(self):
        """modelsReady SHOULD update modelId when there is no current history at all."""
        widget = self._makeWidget()

        realModel = AiModelBase("http://test", model="bar-model")
        realModel.modelsReady.connect(widget._onModelsReady)

        updateCalls = []
        with patch.object(widget, 'currentChatModel', return_value=realModel), \
             patch.object(widget._contextPanel, 'setupModelNames'), \
             patch.object(widget._historyPanel, 'currentHistory', return_value=None), \
             patch.object(widget._historyPanel, 'updateCurrentModelId',
                          side_effect=lambda modelId: updateCalls.append(modelId)):
            realModel.modelsReady.emit()

        self.assertEqual(
            1, len(updateCalls),
            "updateCurrentModelId should be called when there is no history yet",
        )

    def test_modelsReady_selects_history_modelId_in_cbModelNames(self):
        """When models become ready for a loaded history, cbModelNames should show the history's modelId."""
        widget = self._makeWidget()

        realModel = AiModelBase("http://test", model="default-model")
        realModel.modelsReady.connect(widget._onModelsReady)

        fakeHistory = MagicMock()
        fakeHistory.messages = [{"role": "user", "content": "hello"}]
        fakeHistory.modelId = "history-model-id"

        with patch.object(widget, 'currentChatModel', return_value=realModel), \
             patch.object(realModel, 'models', return_value=[
                 ("history-model-id", "History Model"),
                 ("default-model", "Default Model"),
             ]), \
             patch.object(realModel, 'supportsToolCalls', return_value=True), \
             patch.object(widget._historyPanel, 'currentHistory', return_value=fakeHistory), \
             patch.object(widget._historyPanel, 'updateCurrentModelId'):
            realModel.modelsReady.emit()

        self.assertEqual(
            "history-model-id",
            widget._contextPanel.cbModelNames.currentData(),
            "cbModelNames should select the history's modelId, not the model's default",
        )


class TestToolCallResultAutoScroll(TestBase):
    """Regression: _onAgentToolCallResult must auto-scroll when _disableAutoScroll is False."""

    def doCreateRepo(self):
        pass

    def _makeWidget(self) -> AiChatWidget:
        widget = AiChatWidget(parent=None, embedded=False, hideHistoryPanel=True)
        self.processEvents()
        return widget

    def test_toolCallResult_scrolls_to_bottom_when_auto_scroll_enabled(self):
        """_onAgentToolCallResult should call _scrollToBottom() when _disableAutoScroll is False."""
        widget = self._makeWidget()
        widget._disableAutoScroll = False

        scrollCalls = []
        with patch.object(widget, '_scrollToBottom',
                          side_effect=lambda: scrollCalls.append(1)):
            widget._onAgentToolCallResult("id-1", "read_file", "file content", False)

        self.assertEqual(
            1, len(scrollCalls),
            "_scrollToBottom should be called once after a tool call result",
        )

    def test_toolCallResult_does_not_scroll_when_auto_scroll_disabled(self):
        """_onAgentToolCallResult must NOT scroll when _disableAutoScroll is True."""
        widget = self._makeWidget()
        widget._disableAutoScroll = True

        scrollCalls = []
        with patch.object(widget, '_scrollToBottom',
                          side_effect=lambda: scrollCalls.append(1)):
            widget._onAgentToolCallResult("id-1", "read_file", "file content", False)

        self.assertEqual(
            0, len(scrollCalls),
            "_scrollToBottom should NOT be called when auto-scroll is disabled",
        )

    def test_toolCallResult_scrolls_on_error_result(self):
        """_onAgentToolCallResult should also scroll for error results."""
        widget = self._makeWidget()
        widget._disableAutoScroll = False

        scrollCalls = []
        with patch.object(widget, '_scrollToBottom',
                          side_effect=lambda: scrollCalls.append(1)):
            widget._onAgentToolCallResult("id-1", "read_file", "something went wrong", True)

        self.assertEqual(
            1, len(scrollCalls),
            "_scrollToBottom should be called for error tool call results too",
        )


class TestReasoningDeltaAutoScroll(TestBase):
    """Regression: _onAgentReasoningDelta must auto-scroll when _disableAutoScroll is False."""

    def doCreateRepo(self):
        pass

    def _makeWidget(self) -> AiChatWidget:
        widget = AiChatWidget(parent=None, embedded=False, hideHistoryPanel=True)
        self.processEvents()
        return widget

    def test_reasoningDelta_scrolls_to_bottom_when_auto_scroll_enabled(self):
        """_onAgentReasoningDelta should call _scrollToBottom() when _disableAutoScroll is False."""
        widget = self._makeWidget()
        widget._disableAutoScroll = False

        scrollCalls = []
        with patch.object(widget, '_scrollToBottom',
                          side_effect=lambda: scrollCalls.append(1)):
            widget._onAgentReasoningDelta("Thinking...")

        self.assertEqual(
            1, len(scrollCalls),
            "_scrollToBottom should be called once during a reasoning delta",
        )

    def test_reasoningDelta_does_not_scroll_when_auto_scroll_disabled(self):
        """_onAgentReasoningDelta must NOT scroll when _disableAutoScroll is True."""
        widget = self._makeWidget()
        widget._disableAutoScroll = True

        scrollCalls = []
        with patch.object(widget, '_scrollToBottom',
                          side_effect=lambda: scrollCalls.append(1)):
            widget._onAgentReasoningDelta("Thinking...")

        self.assertEqual(
            0, len(scrollCalls),
            "_scrollToBottom should NOT be called when auto-scroll is disabled",
        )


class TestCreateNewConversation(TestBase):
    """Tests for _createNewConversation: empty conversations must bypass the store."""

    def doCreateRepo(self):
        pass

    def _makeWidget(self) -> AiChatWidget:
        widget = AiChatWidget(parent=None, embedded=False, hideHistoryPanel=True)
        self.processEvents()
        return widget

    # ------------------------------------------------------------------
    # Test 1: New conversation inserts directly into model, not via store
    # ------------------------------------------------------------------
    def test_createNewConversation_inserts_into_model_not_store(self):
        """_createNewConversation should call store.model().insertHistory, not store.insertHistoryAtTop."""
        widget = self._makeWidget()

        fakeModel = MagicMock()
        fakeModel.modelId = "test-model"
        fakeModel.name = "Test Model"
        fakeModel.modelKey = "GithubCopilot"

        store = ApplicationBase.instance().aiChatHistoryStore()
        originalInsertCount = store.model().rowCount()

        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(widget._contextPanel, 'cbBots', new_callable=PropertyMock) as mockCbBots, \
             patch.object(widget._historyPanel, 'historyModel',
                          return_value=store.model()), \
             patch.object(widget._historyPanel, 'setCurrentHistory'), \
             patch.object(widget, '_clearCurrentChat'), \
             patch.object(widget, '_setEmbeddedRecentListVisible'):

            widget._createNewConversation()

        # Should have inserted one new history into the model
        self.assertEqual(
            originalInsertCount + 1,
            store.model().rowCount(),
            "A new history should be inserted into the model",
        )

        # The new history should be at the top
        newHistory = store.model().getHistory(0)
        self.assertIsNotNone(newHistory)
        self.assertEqual(newHistory.modelId, "test-model")
        self.assertEqual(newHistory.messages, [],
                         "New conversation should have no messages")

    # ------------------------------------------------------------------
    # Test 2: Empty conversation is NOT persisted to settings
    # ------------------------------------------------------------------
    def test_createNewConversation_does_not_persist_empty(self):
        """_createNewConversation must NOT call _scheduleSave on the store."""
        widget = self._makeWidget()

        fakeModel = MagicMock()
        fakeModel.modelId = "test-model"
        fakeModel.name = "Test Model"
        fakeModel.modelKey = "GithubCopilot"

        store = ApplicationBase.instance().aiChatHistoryStore()

        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(widget._contextPanel, 'cbBots', new_callable=PropertyMock) as mockCbBots, \
             patch.object(widget._historyPanel, 'historyModel',
                          return_value=store.model()), \
             patch.object(widget._historyPanel, 'setCurrentHistory'), \
             patch.object(widget, '_clearCurrentChat'), \
             patch.object(widget, '_setEmbeddedRecentListVisible'), \
             patch.object(store, '_scheduleSave') as mockSave:

            widget._createNewConversation()

        mockSave.assert_not_called()

    # ------------------------------------------------------------------
    # Test 3: Reuses existing empty conversation instead of creating new
    # ------------------------------------------------------------------
    def test_createNewConversation_reuses_existing_empty(self):
        """If an empty conversation already exists at top, _createNewConversation should reuse it."""
        widget = self._makeWidget()

        fakeModel = MagicMock()
        fakeModel.modelId = "test-model"
        fakeModel.name = "Test Model"
        fakeModel.modelKey = "GithubCopilot"

        store = ApplicationBase.instance().aiChatHistoryStore()

        # First call creates an empty conversation
        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(widget._contextPanel, 'cbBots', new_callable=PropertyMock) as mockCbBots, \
             patch.object(widget._historyPanel, 'historyModel',
                          return_value=store.model()), \
             patch.object(widget._historyPanel, 'setCurrentHistory'), \
             patch.object(widget, '_clearCurrentChat'), \
             patch.object(widget, '_setEmbeddedRecentListVisible'):

            widget._createNewConversation()

        firstCount = store.model().rowCount()

        # Second call should reuse the existing empty conversation
        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(widget._contextPanel, 'cbBots', new_callable=PropertyMock) as mockCbBots, \
             patch.object(widget._historyPanel, 'historyModel',
                          return_value=store.model()), \
             patch.object(widget._historyPanel, 'setCurrentHistory'), \
             patch.object(widget, '_clearCurrentChat'), \
             patch.object(widget, '_setEmbeddedRecentListVisible'):

            widget._createNewConversation()

        self.assertEqual(
            firstCount,
            store.model().rowCount(),
            "Should not create a new history when an empty one already exists",
        )

    # ------------------------------------------------------------------
    # Test 4: Creates new when top history has messages
    # ------------------------------------------------------------------
    def test_createNewConversation_creates_new_when_top_has_messages(self):
        """If the top history has messages, _createNewConversation should create a new one."""
        widget = self._makeWidget()

        fakeModel = MagicMock()
        fakeModel.modelId = "test-model"
        fakeModel.name = "Test Model"
        fakeModel.modelKey = "GithubCopilot"

        store = ApplicationBase.instance().aiChatHistoryStore()

        # Insert a non-empty history at top
        nonEmpty = AiChatHistory(messages=[{"role": "user", "content": "hi"}])
        store.model().insertHistory(0, nonEmpty)
        initialCount = store.model().rowCount()

        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(widget._contextPanel, 'cbBots', new_callable=PropertyMock) as mockCbBots, \
             patch.object(widget._historyPanel, 'historyModel',
                          return_value=store.model()), \
             patch.object(widget._historyPanel, 'setCurrentHistory'), \
             patch.object(widget, '_clearCurrentChat'), \
             patch.object(widget, '_setEmbeddedRecentListVisible'):

            widget._createNewConversation()

        self.assertEqual(
            initialCount + 1,
            store.model().rowCount(),
            "Should create a new history when the top one has messages",
        )


if __name__ == "__main__":
    unittest.main()
