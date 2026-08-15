"""Isolated tests for the Teams AppModule and global plugin."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


class _Role:
	GROUPING = 1
	LISTITEM = 2


class _AppModuleBase:
	def __init__(self, *args, **kwargs):
		pass

	def terminate(self):
		pass


class _GlobalPluginBase:
	def __init__(self, *args, **kwargs):
		pass

	def terminate(self, *args, **kwargs):
		pass


class _BrailleRegion:
	def __init__(self, rawText=""):
		self.rawText = rawText
		self.rawTextTypeforms = None
		self.cursorPos = None
		self.selectionStart = None
		self.selectionEnd = None
		self.brailleCells = []

	def update(self):
		self.brailleCells = list(self.rawText)


class _BrailleBuffer:
	def __init__(self, regions=()):
		self.visibleRegions = list(regions)
		self.rawText = ""
		self.brailleCells = []

	def update(self):
		self.rawText = "".join(region.rawText for region in self.visibleRegions)
		self.brailleCells = [cell for region in self.visibleRegions for cell in region.brailleCells]


class _BrailleHandler:
	def __init__(self):
		self.mainBuffer = object()
		self.messageBuffer = object()
		self.buffer = self.mainBuffer
		self.messages = []

	def message(self, text):
		self.messages.append(text)
		self.buffer = self.messageBuffer


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


registrationCalls = []
uiMessages = []
uiaClient = _UIAClient()


def _registerExecutable(executableName, appModuleName):
	registrationCalls.append(("register", executableName, appModuleName))


def _unregisterExecutable(executableName):
	registrationCalls.append(("unregister", executableName))


stubs = {
	"api": types.SimpleNamespace(
		getFocusObject=lambda: None,
		getForegroundObject=lambda: types.SimpleNamespace(windowHandle=100),
	),
	"appModuleHandler": types.SimpleNamespace(
		AppModule=_AppModuleBase,
		registerExecutableWithAppModule=_registerExecutable,
		unregisterExecutable=_unregisterExecutable,
	),
	"controlTypes": types.SimpleNamespace(Role=_Role),
	"globalPluginHandler": types.SimpleNamespace(GlobalPlugin=_GlobalPluginBase),
	"braille": types.SimpleNamespace(
		Region=_BrailleRegion,
		BrailleBuffer=_BrailleBuffer,
		BrailleHandler=_BrailleHandler,
	),
	"logHandler": types.SimpleNamespace(
		log=types.SimpleNamespace(debugWarning=lambda *args, **kwargs: None),
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

repoRoot = Path(__file__).resolve().parents[3]
appModulePath = repoRoot / "addon" / "appModules" / "ms_teams.py"
appModuleSpec = importlib.util.spec_from_file_location("msTeamsTestAppModule", appModulePath)
appModule = importlib.util.module_from_spec(appModuleSpec)
assert appModuleSpec.loader is not None
appModuleSpec.loader.exec_module(appModule)

appModulesPackage = types.ModuleType("appModules")
appModulesPackage.__path__ = []
sys.modules["appModules"] = appModulesPackage
sys.modules["appModules.ms_teams"] = appModule

globalPluginPath = repoRoot / "addon" / "globalPlugins" / "msTeamsMessageHelpFilter.py"
globalPluginSpec = importlib.util.spec_from_file_location("msTeamsTestGlobalPlugin", globalPluginPath)
globalPlugin = importlib.util.module_from_spec(globalPluginSpec)
assert globalPluginSpec.loader is not None
globalPluginSpec.loader.exec_module(globalPlugin)


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

	def testPunctuationResidueBecomesEmpty(self):
		self.assertEqual(appModule.filterNavigationHelp("Press Enter to explore message content. ."), "")
		self.assertEqual(appModule.filterNavigationHelp("Press Enter to explore message content…."), "")

	def testUnrelatedContentIsUnchanged(self):
		self.assertEqual(appModule.filterNavigationHelp("Press Enter to send the message."), "Press Enter to send the message.")

	def testMultilineContentIsPreserved(self):
		text = "First line\nSecond line\nPress Enter to explore message content."
		self.assertEqual(appModule.filterNavigationHelp(text), "First line\nSecond line")


class RecentMessageTests(unittest.TestCase):
	def setUp(self):
		uiMessages.clear()
		uiaClient.elements = []
		stubs["api"].getFocusObject = lambda: None

	def testReadsNewestFirstWithoutMovingFocus(self):
		oldFocus = object()
		stubs["api"].getFocusObject = lambda: oldFocus
		uiaClient.elements = [
			_UIAElement("unrelated-group", "Navigation"),
			_UIAElement("message-body-100", "Older message Alice Today at 1:00 PM."),
			_UIAElement("message-body-200", "Newest message Bob Today at 1:01 PM."),
		]
		instance = appModule.AppModule()
		try:
			instance.script_readRecentMessage(types.SimpleNamespace(mainKeyName="1"))
			instance.script_readRecentMessage(types.SimpleNamespace(mainKeyName="2"))
			self.assertEqual(
				uiMessages,
				[
					"Newest message Bob Today at 1:01 PM.",
					"Older message Alice Today at 1:00 PM.",
				],
			)
			self.assertIs(stubs["api"].getFocusObject(), oldFocus)
		finally:
			instance.terminate()

	def testReportsVirtualizedMessageUnavailable(self):
		uiaClient.elements = [_UIAElement("message-body-200", "Only rendered message")]
		instance = appModule.AppModule()
		try:
			instance.script_readRecentMessage(types.SimpleNamespace(mainKeyName="3"))
			self.assertEqual(uiMessages, ["Recent message 3 is not available"])
		finally:
			instance.terminate()

	def testGesturesCoverOneThroughNine(self):
		self.assertEqual(
			appModule.AppModule.script_readRecentMessage.gestures,
			[f"kb:control+shift+{number}" for number in range(1, 10)],
		)


class GlobalPluginTests(unittest.TestCase):
	def setUp(self):
		registrationCalls.clear()
		stubs["api"].getFocusObject = lambda: None

	def testExecutableMappingIsRegisteredAndRestored(self):
		originalUpdate = _BrailleBuffer.update
		originalMessage = _BrailleHandler.message
		plugin = globalPlugin.GlobalPlugin()
		self.assertEqual(registrationCalls, [("register", "ms-teams", "ms_teams")])
		plugin.terminate()
		self.assertEqual(registrationCalls[-1], ("unregister", "ms-teams"))
		self.assertIs(_BrailleBuffer.update, originalUpdate)
		self.assertIs(_BrailleHandler.message, originalMessage)

	def testInstructionDoesNotActivateMessageBuffer(self):
		teamsApp = types.SimpleNamespace(appName="ms-teams")
		focus = types.SimpleNamespace(appModule=teamsApp)
		stubs["api"].getFocusObject = lambda: focus
		plugin = globalPlugin.GlobalPlugin()
		try:
			handler = _BrailleHandler()
			handler.message("Press Enter to explore message content.")
			self.assertEqual(handler.messages, [])
			self.assertIs(handler.buffer, handler.mainBuffer)
		finally:
			plugin.terminate()

	def testBrailleRegionIsRetranslated(self):
		text = "Hello. Press Enter to explore message content. group"
		region = _BrailleRegion(text)
		region.rawTextTypeforms = list(range(len(text)))
		region.cursorPos = len(text)
		self.assertTrue(globalPlugin._filterBrailleRegion(region))
		self.assertEqual(region.rawText, "Hello. group")
		self.assertNotIn("explore message", "".join(region.brailleCells).lower())
		self.assertEqual(len(region.rawTextTypeforms), len(region.rawText))
		self.assertEqual(region.cursorPos, len(region.rawText))


if __name__ == "__main__":
	unittest.main()
