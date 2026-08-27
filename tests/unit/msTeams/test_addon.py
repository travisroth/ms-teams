"""Isolated tests for the Teams AppModule.

The add-on has no global plugin. ``addon/appModules/ms-teams.py`` is named after
the executable, so NVDA loads it for ``ms-teams.exe`` without any registration.
The hyphen keeps it out of normal import syntax, hence the loader below.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


class _Role:
	"""Only the two roles this module compares against."""

	GROUPING = 1
	LISTITEM = 2


class _State:
	EDITABLE = "editable"
	READONLY = "readonly"


class _AppModuleBase:
	def __init__(self, *args, **kwargs):
		pass

	def terminate(self):
		pass


class _NVDAObjectTextInfo:
	"""Stand-in for NVDA's default TextInfo, which exposes basicText."""


class _NVDAObjectBase:
	"""Stand-in for NVDAObject.

	Only used as a base class for the overlay. NVDA's auto property metaclass
	cannot be reproduced here, so the overlay's property behaviour is exercised
	in NVDA itself rather than in these tests.
	"""

	def _get_name(self):
		return ""

	def _get_description(self):
		return ""

	def _get_value(self):
		return ""

	def _get_placeholder(self):
		return ""

	def _get_errorMessage(self):
		return ""

	def _get_states(self):
		return set(getattr(self, "baseStates", ()))


class _BrailleHandler:
	"""Mirrors the shape the add-on relies on.

	``message`` is a class level method, so assigning to ``handler.message``
	creates an instance attribute and deleting it exposes the method again,
	exactly as with NVDA's real handler.
	"""

	def __init__(self):
		self.messages = []

	def message(self, text):
		self.messages.append(text)


class _UIAElement:
	def __init__(self, automationId, name):
		self.cachedAutomationId = automationId
		self.cachedName = name

	def buildUpdatedCache(self, cacheRequest):
		return self


class _UIAElementCollection:
	def __init__(self, elements):
		self._elements = list(elements)
		self.length = len(self._elements)

	def getElement(self, index):
		return self._elements[index]


class _UIARoot:
	def __init__(self, client):
		self._client = client

	def findAll(self, treeScope, condition):
		return _UIAElementCollection(self._client.elements)


class _UIAClient:
	def __init__(self):
		self.elements = []

	def elementFromHandle(self, windowHandle):
		return _UIARoot(self)

	def createPropertyCondition(self, propertyId, value):
		return (propertyId, value)


def _scriptDecorator(**metadata):
	def decorate(function):
		function.gestures = list(metadata.get("gestures", ()))
		return function

	return decorate


uiMessages = []
uiaClient = _UIAClient()
brailleHandler = _BrailleHandler()

stubs = {
	"api": types.SimpleNamespace(
		getFocusObject=lambda: None,
		getForegroundObject=lambda: types.SimpleNamespace(windowHandle=100),
	),
	"appModuleHandler": types.SimpleNamespace(AppModule=_AppModuleBase),
	"braille": types.SimpleNamespace(handler=brailleHandler),
	"controlTypes": types.SimpleNamespace(Role=_Role, State=_State),
	"logHandler": types.SimpleNamespace(
		log=types.SimpleNamespace(
			debugWarning=lambda *args, **kwargs: None,
			info=lambda *args, **kwargs: None,
		),
	),
	"NVDAObjects": types.SimpleNamespace(
		NVDAObject=_NVDAObjectBase,
		NVDAObjectTextInfo=_NVDAObjectTextInfo,
	),
	"scriptHandler": types.SimpleNamespace(script=_scriptDecorator),
	"UIAHandler": types.SimpleNamespace(
		handler=types.SimpleNamespace(clientObject=uiaClient, baseCacheRequest=object()),
		UIA_ControlTypePropertyId=1,
		UIA_GroupControlTypeId=2,
		TreeScope_Descendants=4,
	),
	"ui": types.SimpleNamespace(message=lambda text: uiMessages.append(text)),
}

for name, stub in stubs.items():
	sys.modules[name] = stub

# No speech stub: the add-on falls back to filter_speechSequence = None and the
# filter is called directly below instead of through the extension point.

repoRoot = Path(__file__).resolve().parents[3]
appModulePath = repoRoot / "addon" / "appModules" / "ms-teams.py"
appModuleSpec = importlib.util.spec_from_file_location("msTeamsTestAppModule", appModulePath)
appModule = importlib.util.module_from_spec(appModuleSpec)
assert appModuleSpec.loader is not None
appModuleSpec.loader.exec_module(appModule)


class _Ia2Object:
	"""A stand-in for a non-message node in the history tree."""

	def __init__(self, elementId="", role=_Role.GROUPING, firstChild=None):
		self.IA2Attributes = {"id": elementId} if elementId else {}
		self.role = role
		self.firstChild = firstChild
		self.next = None
		self.previous = None
		self.parent = None


def _buildHistory(shape):
	"""Build a chain of wrappers from a shape of message ids and gaps.

	An entry of None makes a wrapper holding no message, which is what Teams
	produces for timestamps and for the emoji pop-over beside a focused message.
	Returns the declared container and the messages, keyed by id.
	"""
	wrappers = []
	messages = {}
	container = appModule.TeamsMessageList()
	container.IA2Attributes = {"id": "chat-pane-list"}
	for entry in shape:
		wrapper = _Ia2Object(role=_Role.GROUPING)
		wrapper.parent = container
		if entry is not None:
			message = appModule.TeamsMessage()
			message.IA2Attributes = {"id": entry}
			message.firstChild = None
			message.next = None
			message.parent = wrapper
			wrapper.firstChild = message
			messages[entry] = message
		wrappers.append(wrapper)
	for index, wrapper in enumerate(wrappers):
		wrapper.previous = wrappers[index - 1] if index else None
		wrapper.next = wrappers[index + 1] if index + 1 < len(wrappers) else None
	container.firstChild = wrappers[0] if wrappers else None
	container.lastChild = wrappers[-1] if wrappers else None
	return container, messages


class _TeamsAppModuleFixture(unittest.TestCase):
	"""Creates an AppModule with a focus object that belongs to it."""

	def setUp(self):
		uiMessages.clear()
		uiaClient.elements = []
		brailleHandler.messages.clear()
		self.instance = appModule.AppModule()
		self.addCleanup(self.instance.terminate)
		self.addCleanup(setattr, stubs["api"], "getFocusObject", lambda: None)

	def focusTeams(self):
		focus = types.SimpleNamespace(appModule=self.instance)
		stubs["api"].getFocusObject = lambda: focus

	def focusElsewhere(self):
		focus = types.SimpleNamespace(appModule=object())
		stubs["api"].getFocusObject = lambda: focus


class NavigationHelpTests(unittest.TestCase):
	def testCurrentWordingIsRemoved(self):
		text = (
			"Hello from Travis. Press Enter to explore message content, then use "
			"Escape to shift focus back to the message."
		)
		self.assertEqual(appModule.filterNavigationHelp(text), "Hello from Travis.")

	def testOlderWordingIsRemoved(self):
		text = (
			"Hello. Press Enter to explore message content, then use Escape to shift "
			"focus back to navigate through the message stream. Use up and down arrow "
			"to navigate to other messages."
		)
		self.assertEqual(appModule.filterNavigationHelp(text), "Hello.")

	def testInstructionOnlyBecomesEmpty(self):
		self.assertEqual(appModule.filterNavigationHelp("Press Enter to explore message content."), "")

	def testLiveRegionWordingBecomesEmpty(self):
		# Captured verbatim from a Chromium live region, trailing space included.
		text = "Press Enter to explore message content, then use Escape to shift focus back to the message.. "
		self.assertEqual(appModule.filterNavigationHelp(text), "")

	def testPunctuationResidueBecomesEmpty(self):
		self.assertEqual(appModule.filterNavigationHelp("Press Enter to explore message content. ."), "")
		self.assertEqual(appModule.filterNavigationHelp("Press Enter to explore message content…."), "")

	def testUnrelatedContentIsUnchanged(self):
		self.assertEqual(
			appModule.filterNavigationHelp("Press Enter to send the message."),
			"Press Enter to send the message.",
		)

	def testMultilineContentIsPreserved(self):
		text = "First line\nSecond line\nPress Enter to explore message content."
		self.assertEqual(appModule.filterNavigationHelp(text), "First line\nSecond line")


class SuppressedAnnouncementTests(unittest.TestCase):
	def testFilterCountIsSuppressed(self):
		for text in ("7 results ", "7 results", "1 result", "0 results", "No results"):
			with self.subTest(text=text):
				self.assertTrue(appModule.isSuppressedAnnouncement(text))

	def testSendProgressIsSuppressed(self):
		for text in ("Sending", "Sending... ", "Message sent", "Message sent ", "Sent!"):
			with self.subTest(text=text):
				self.assertTrue(appModule.isSuppressedAnnouncement(text))

	def testFailuresAreStillAnnounced(self):
		for text in ("Message not sent", "Failed to send message", "Resending"):
			with self.subTest(text=text):
				self.assertFalse(appModule.isSuppressedAnnouncement(text))

	def testIncomingMessagesAreStillAnnounced(self):
		for text in (
			"Message from Ryan Praeuner. heres another message! ",
			"Unread message Chat Ryan Praeuner Available",
			"7 results found in chat",
		):
			with self.subTest(text=text):
				self.assertFalse(appModule.isSuppressedAnnouncement(text))


class BrailleMessageFilterTests(_TeamsAppModuleFixture):
	def testNavigationHelpNeverReachesTheDisplay(self):
		self.focusTeams()
		appModule.braille.handler.message("Press Enter to explore message content.")
		self.assertEqual(brailleHandler.messages, [])

	def testSuppressedAnnouncementsNeverReachTheDisplay(self):
		self.focusTeams()
		appModule.braille.handler.message("7 results ")
		appModule.braille.handler.message("Message sent ")
		self.assertEqual(brailleHandler.messages, [])

	def testUsefulAnnouncementsAreUntouched(self):
		self.focusTeams()
		appModule.braille.handler.message("Message from Ryan Praeuner. hello! ")
		self.assertEqual(brailleHandler.messages, ["Message from Ryan Praeuner. hello! "])

	def testEmbeddedHelpIsStrippedFromRealContent(self):
		self.focusTeams()
		appModule.braille.handler.message("Ryan: see attached. Press Enter to explore message content.")
		self.assertEqual(brailleHandler.messages, ["Ryan: see attached."])

	def testOtherApplicationsAreUnaffected(self):
		self.focusElsewhere()
		appModule.braille.handler.message("7 results ")
		self.assertEqual(brailleHandler.messages, ["7 results "])

	def testHandlerIsRestoredOnTerminate(self):
		original = _BrailleHandler.message
		self.instance.terminate()
		self.assertIs(type(brailleHandler).message, original)
		self.assertNotIn("message", brailleHandler.__dict__)
		# terminate runs again via addCleanup, which must stay harmless.


class SpeechFilterTests(_TeamsAppModuleFixture):
	def testSuppressedAnnouncementSilencesTheSequence(self):
		self.focusTeams()
		self.assertEqual(self.instance._filterSpeechSequence(["7 results "]), [])

	def testNavigationHelpIsStripped(self):
		self.focusTeams()
		self.assertEqual(
			self.instance._filterSpeechSequence(["Ryan: hi. Press Enter to explore message content."]),
			["Ryan: hi."],
		)

	def testNonStringCommandsSurvive(self):
		self.focusTeams()
		command = object()
		self.assertEqual(
			self.instance._filterSpeechSequence([command, "Press Enter to explore message content."]),
			[command, ""],
		)

	def testOtherApplicationsAreUnaffected(self):
		self.focusElsewhere()
		sequence = ["7 results "]
		self.assertIs(self.instance._filterSpeechSequence(sequence), sequence)


class RecentMessageTests(_TeamsAppModuleFixture):
	def testReadsNewestFirstWithoutMovingFocus(self):
		oldFocus = object()
		stubs["api"].getFocusObject = lambda: oldFocus
		uiaClient.elements = [
			_UIAElement("unrelated-group", "Navigation"),
			_UIAElement("message-body-100", "Older message Alice Today at 1:00 PM."),
			_UIAElement("message-body-200", "Newest message Bob Today at 1:01 PM."),
		]
		self.instance.script_readRecentMessage(types.SimpleNamespace(mainKeyName="1"))
		self.instance.script_readRecentMessage(types.SimpleNamespace(mainKeyName="2"))
		self.assertEqual(
			uiMessages,
			[
				"Newest message Bob Today at 1:01 PM.",
				"Older message Alice Today at 1:00 PM.",
			],
		)
		self.assertIs(stubs["api"].getFocusObject(), oldFocus)

	def testReportsVirtualizedMessageUnavailable(self):
		uiaClient.elements = [_UIAElement("message-body-200", "Only rendered message")]
		self.instance.script_readRecentMessage(types.SimpleNamespace(mainKeyName="3"))
		self.assertEqual(uiMessages, ["Recent message 3 is not available"])

	def testGesturesCoverOneThroughNine(self):
		self.assertEqual(
			appModule.AppModule.script_readRecentMessage.gestures,
			[f"kb:control+shift+{number}" for number in range(1, 10)],
		)


class MessageDetectionTests(unittest.TestCase):
	def testMessageBodiesAreRecognised(self):
		self.assertTrue(appModule._isMessageObject(_Ia2Object("message-body-1234")))

	def testOtherGroupingsAreNot(self):
		self.assertFalse(appModule._isMessageObject(_Ia2Object("chat-list-item-9")))
		self.assertFalse(appModule._isMessageObject(_Ia2Object()))

	def testOtherRolesAreNotEvenWithAMatchingId(self):
		self.assertFalse(
			appModule._isMessageObject(_Ia2Object("message-body-1234", role=_Role.LISTITEM)),
		)

	def testContainerIsRecognisedByItsId(self):
		self.assertTrue(appModule._isMessageListObject(_Ia2Object("chat-pane-list")))
		self.assertFalse(appModule._isMessageListObject(_Ia2Object("menur1ri")))
		self.assertFalse(appModule._isMessageListObject(_Ia2Object()))

	def testOverlayChoiceFollowsDetection(self):
		instance = appModule.AppModule()
		try:
			for obj, expected in (
				(_Ia2Object("message-body-1"), appModule.TeamsMessage),
				(_Ia2Object("chat-pane-list"), appModule.TeamsMessageList),
				(_Ia2Object("something-else"), appModule.TeamsMessageHelpFilterOverlay),
			):
				clsList = []
				instance.chooseNVDAObjectOverlayClasses(obj, clsList)
				self.assertIs(clsList[0], expected)
		finally:
			instance.terminate()


class MultilineFlowTests(unittest.TestCase):
	def testMessagesReportAsListItems(self):
		# LISTITEM is in silentRolesOnFocus, so NVDA drops the role text for a
		# named object in both speech and braille. GROUPING is not.
		self.assertEqual(appModule.TeamsMessage.role, _Role.LISTITEM)

	def testRunIsDeclared(self):
		self.assertTrue(appModule.TeamsMessage.brlMultilineFlowRun)

	def testMessagesAreReadFromTheirOwnProperties(self):
		# Chromium exposes IAccessibleText on the message div, but the div's own
		# text is a single space, which left report current line reading a blank.
		self.assertIs(appModule.TeamsMessage.TextInfo, _NVDAObjectTextInfo)

	def testWalksForwardAndBack(self):
		_, messages = _buildHistory(["message-body-1", "message-body-2", "message-body-3"])
		first, second, third = (messages[f"message-body-{n}"] for n in (1, 2, 3))
		self.assertIs(first.brlMultilineFlowNext(), second)
		self.assertIs(second.brlMultilineFlowNext(), third)
		self.assertIs(third.brlMultilineFlowPrevious(), second)
		self.assertIs(second.brlMultilineFlowPrevious(), first)

	def testTerminatesWithoutWrappingAround(self):
		_, messages = _buildHistory(["message-body-1", "message-body-2"])
		self.assertIsNone(messages["message-body-1"].brlMultilineFlowPrevious())
		self.assertIsNone(messages["message-body-2"].brlMultilineFlowNext())

	def testSkipsWrappersHoldingNoMessage(self):
		_, messages = _buildHistory(["message-body-1", None, None, "message-body-2"])
		first, second = messages["message-body-1"], messages["message-body-2"]
		self.assertIs(first.brlMultilineFlowNext(), second)
		self.assertIs(second.brlMultilineFlowPrevious(), first)

	def testDoesNotScanTheWholeHistoryForOneStep(self):
		# A long stretch of message-less wrappers must end the run rather than
		# turn a single pan into a walk of the loaded history.
		_, messages = _buildHistory(["message-body-1"] + [None] * 200 + ["message-body-2"])
		self.assertIsNone(messages["message-body-1"].brlMultilineFlowNext())

	def testFindsAMessageNestedInsideItsWrapper(self):
		_, messages = _buildHistory(["message-body-1", "message-body-2"])
		second = messages["message-body-2"]
		wrapper = second.parent
		# Push the message one level deeper, behind an unnamed element.
		inner = _Ia2Object(firstChild=second)
		wrapper.firstChild = inner
		second.parent = inner
		inner.parent = wrapper
		self.assertIs(messages["message-body-1"].brlMultilineFlowNext(), second)


class PinnedRunTests(unittest.TestCase):
	def testContainerIsDeclared(self):
		self.assertTrue(appModule.TeamsMessageList.brlMultilineFlowRunContainer)

	def testAPinStartsAtTheNewestMessage(self):
		# A chat wants the newest under the fingers. BrlMultiline's own fallback
		# would find the first member, which is right for a list and wrong here.
		container, messages = _buildHistory(["message-body-1", "message-body-2", "message-body-3"])
		self.assertIs(container.brlMultilineFlowRunStart(), messages["message-body-3"])

	def testStartSkipsTrailingWrappersHoldingNoMessage(self):
		container, messages = _buildHistory(["message-body-1", "message-body-2", None, None])
		self.assertIs(container.brlMultilineFlowRunStart(), messages["message-body-2"])

	def testStartWalksBackIntoTheRunFromTheEnd(self):
		container, messages = _buildHistory(["message-body-1", "message-body-2"])
		start = container.brlMultilineFlowRunStart()
		self.assertIs(start, messages["message-body-2"])
		self.assertIs(start.brlMultilineFlowPrevious(), messages["message-body-1"])
		self.assertIsNone(start.brlMultilineFlowNext())

	def testEmptyHistoryHasNoStart(self):
		container, _ = _buildHistory([])
		self.assertIsNone(container.brlMultilineFlowRunStart())

	def testStartDoesNotScanTheWholeHistory(self):
		container, _ = _buildHistory(["message-body-1"] + [None] * 200)
		self.assertIsNone(container.brlMultilineFlowRunStart())


if __name__ == "__main__":
	unittest.main()
