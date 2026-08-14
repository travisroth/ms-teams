# Microsoft Teams Accessibility Enhancements for NVDA
# Copyright (C) 2026 Ryan Praeuner and contributors
# SPDX-License-Identifier: GPL-2.0-or-later
# pyright: basic

"""Register New Teams support and filter its generated braille messages."""

import api
import appModuleHandler
import braille
import globalPluginHandler
from logHandler import log

from appModules.ms_teams import filterNavigationHelp, getNavigationHelpMatchSpans


_EXECUTABLE_NAME = "ms-teams"
_APP_MODULE_NAME = "ms_teams"


def _getObjectAppModule(obj):
	"""Resolve an AppModule from an NVDA object or tree interceptor."""
	for candidate in (obj, getattr(obj, "rootNVDAObject", None)):
		if candidate is None:
			continue
		try:
			return candidate.appModule
		except Exception:
			continue
	return None


def _isNewTeamsObject(obj) -> bool:
	appModule = _getObjectAppModule(obj)
	if appModule is None:
		try:
			appModule = _getObjectAppModule(api.getFocusObject())
		except Exception:
			return False
	if appModule is None:
		return False
	try:
		appName = appModule.appName.lower().replace("_", "-")
	except Exception:
		appName = ""
	if appName == _EXECUTABLE_NAME:
		return True
	try:
		return appModule.__class__.__module__.rsplit(".", 1)[-1] == _APP_MODULE_NAME
	except Exception:
		return False


def _isPresentingRetrievedMessage(obj) -> bool:
	appModule = _getObjectAppModule(obj)
	return bool(getattr(appModule, "_presentingRetrievedMessage", False))


def _adjustTextOffset(offset, spans):
	"""Map an offset from the original region into the shortened region."""
	if offset is None:
		return None
	removedBefore = 0
	for start, end in spans:
		if offset <= start:
			break
		if offset < end:
			return start - removedBefore
		removedBefore += end - start
	return offset - removedBefore


def _removeSpans(value, spans):
	for start, end in reversed(spans):
		value = value[:start] + value[end:]
	return value


def _filterBrailleRegion(region) -> bool:
	"""Remove Teams help from one translated region and rebuild its cells."""
	rawText = getattr(region, "rawText", None)
	spans = getNavigationHelpMatchSpans(rawText)
	if not spans:
		return False

	originalState = {
		attribute: getattr(region, attribute, None)
		for attribute in (
			"rawText",
			"rawTextTypeforms",
			"cursorPos",
			"selectionStart",
			"selectionEnd",
		)
	}
	try:
		region.rawText = _removeSpans(rawText, spans)
		typeforms = originalState["rawTextTypeforms"]
		if typeforms is not None:
			region.rawTextTypeforms = _removeSpans(typeforms, spans)
		for attribute in ("cursorPos", "selectionStart", "selectionEnd"):
			setattr(region, attribute, _adjustTextOffset(originalState[attribute], spans))
		braille.Region.update(region)
		return True
	except Exception:
		for attribute, value in originalState.items():
			setattr(region, attribute, value)
		log.debugWarning("Could not filter a Teams braille region", exc_info=True)
		return False


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Map ``ms-teams.exe`` and install Teams-scoped braille filters."""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		appModuleHandler.registerExecutableWithAppModule(
			_EXECUTABLE_NAME,
			_APP_MODULE_NAME,
		)
		self._originalBrailleBufferUpdate = braille.BrailleBuffer.update

		def filterBrailleBufferUpdate(buffer, *updateArgs, **updateKwargs):
			try:
				focus = api.getFocusObject()
			except Exception:
				focus = None
			if _isNewTeamsObject(focus) and not _isPresentingRetrievedMessage(focus):
				for region in tuple(buffer.visibleRegions):
					_filterBrailleRegion(region)
			return self._originalBrailleBufferUpdate(buffer, *updateArgs, **updateKwargs)

		self._brailleBufferUpdateFilter = filterBrailleBufferUpdate
		braille.BrailleBuffer.update = self._brailleBufferUpdateFilter

		self._originalBrailleHandlerMessage = braille.BrailleHandler.message

		def filterBrailleMessage(handler, text, *messageArgs, **messageKwargs):
			try:
				focus = api.getFocusObject()
			except Exception:
				focus = None
			if _isNewTeamsObject(focus) and not _isPresentingRetrievedMessage(focus):
				filteredText = filterNavigationHelp(text)
				if not filteredText:
					return
				text = filteredText
			return self._originalBrailleHandlerMessage(handler, text, *messageArgs, **messageKwargs)

		self._brailleHandlerMessageFilter = filterBrailleMessage
		braille.BrailleHandler.message = self._brailleHandlerMessageFilter

	def terminate(self, *args, **kwargs):
		try:
			if braille.BrailleBuffer.update is self._brailleBufferUpdateFilter:
				braille.BrailleBuffer.update = self._originalBrailleBufferUpdate
			if braille.BrailleHandler.message is self._brailleHandlerMessageFilter:
				braille.BrailleHandler.message = self._originalBrailleHandlerMessage
		finally:
			try:
				appModuleHandler.unregisterExecutable(_EXECUTABLE_NAME)
			finally:
				super().terminate(*args, **kwargs)
