# Microsoft Teams Accessibility Enhancements for NVDA
# Copyright (C) 2026 Ryan Praeuner and contributors
# SPDX-License-Identifier: GPL-2.0-or-later
# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

"""Improve message navigation and presentation in the New Microsoft Teams client."""

from __future__ import annotations

import re
import time
from typing import Optional, Sequence, Tuple
import unicodedata

import api
import appModuleHandler
import controlTypes
from logHandler import log
import scriptHandler
import ui
import UIAHandler

try:
	from speech.extensions import filter_speechSequence
except (ImportError, AttributeError):
	filter_speechSequence = None


_NAVIGATION_HELP_RE = re.compile(
	r"""
	\s*
	press\s+enter\s+to\s+explore\s+message\s+content
	(?:
		,?\s*then\s+use\s+escape\s+to\s+shift\s+focus\s+back
		(?:
			\s+to\s+
			(?:
				the\s+message
				|
				navigate\s+through\s+the\s+message\s+stream
			)
		)?
	)?
	(?:[ \t]*[.!?…])*
	(?:
		\s*use\s+(?:the\s+)?up\s+and\s+down\s+arrow(?:\s+keys?)?
		\s+to\s+navigate\s+to\s+other\s+messages(?:[ \t]*[.!?…])*
	)?
	""",
	re.IGNORECASE | re.VERBOSE,
)

_PUNCTUATION_NOTIFICATION_GRACE_SECONDS = 0.75
_MESSAGE_AUTOMATION_ID_PREFIX = "message-body-"
_RECENT_MESSAGE_GESTURES = tuple(f"kb:control+shift+{number}" for number in range(1, 10))


def _containsOnlyPunctuationOrSpacing(text: object) -> bool:
	return (
		isinstance(text, str)
		and bool(text)
		and all(
			character.isspace()
			or unicodedata.category(character).startswith(("P", "Z"))
			or unicodedata.category(character) == "Cf"
			for character in text
		)
	)


def filterNavigationHelp(text: Optional[str]) -> Optional[str]:
	"""Remove the Teams message-navigation instruction from ``text``."""
	if not isinstance(text, str) or not text:
		return text
	hadNavigationHelp = _NAVIGATION_HELP_RE.search(text) is not None
	filtered = _NAVIGATION_HELP_RE.sub("", text)
	filtered = re.sub(r"[ \t]{2,}", " ", filtered)
	filtered = re.sub(r"[ \t]*\n[ \t]*", "\n", filtered)
	filtered = filtered.strip()
	if hadNavigationHelp and _containsOnlyPunctuationOrSpacing(filtered):
		return ""
	return filtered


def getNavigationHelpMatchSpans(text: object) -> Tuple[Tuple[int, int], ...]:
	"""Return source offsets for every Teams navigation-help instruction."""
	if not isinstance(text, str) or not text:
		return ()
	return tuple(match.span() for match in _NAVIGATION_HELP_RE.finditer(text))


def _containsNavigationHelp(text: object) -> bool:
	return isinstance(text, str) and _NAVIGATION_HELP_RE.search(text) is not None


def _filterObjectProperties(obj) -> None:
	"""Replace cached object text when Teams supplies the help dynamically."""
	for attribute in ("name", "description", "value"):
		try:
			rawText = getattr(obj, attribute, None)
		except Exception:
			continue
		if not _containsNavigationHelp(rawText):
			continue
		try:
			setattr(obj, attribute, filterNavigationHelp(rawText))
		except Exception:
			log.debugWarning(
				f"Could not cache filtered Teams {attribute}",
				exc_info=True,
			)


class TeamsMessageHelpFilterOverlay:
	"""Dynamically clean accessible properties used by speech and braille."""

	def _get_name(self):
		return filterNavigationHelp(super()._get_name())

	def _get_description(self):
		return filterNavigationHelp(super()._get_description())

	def _get_value(self):
		return filterNavigationHelp(super()._get_value())


class AppModule(appModuleHandler.AppModule):
	"""NVDA support for ``ms-teams.exe`` (New Microsoft Teams)."""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._speechFilterRegistered = False
		self._suppressPunctuationNotificationUntil = 0.0
		self._presentingRetrievedMessage = False
		if filter_speechSequence is not None:
			filter_speechSequence.register(self._filterSpeechSequence)
			self._speechFilterRegistered = True

	def terminate(self):
		if self._speechFilterRegistered and filter_speechSequence is not None:
			try:
				filter_speechSequence.unregister(self._filterSpeechSequence)
			except Exception:
				log.debugWarning("Could not unregister Teams speech filter", exc_info=True)
		self._speechFilterRegistered = False
		super().terminate()

	def _isThisTeamsInstanceFocused(self) -> bool:
		try:
			focus = api.getFocusObject()
			return focus is not None and focus.appModule is self
		except Exception:
			return False

	def _filterSpeechSequence(self, speechSequence: Sequence[object]):
		"""Filter late-added Teams help immediately before synthesis."""
		if self._presentingRetrievedMessage or not self._isThisTeamsInstanceFocused():
			return speechSequence
		changed = False
		filteredSequence = []
		for item in speechSequence:
			if isinstance(item, str):
				filteredItem = filterNavigationHelp(item)
				changed = changed or filteredItem != item
				filteredSequence.append(filteredItem)
			else:
				filteredSequence.append(item)
		return filteredSequence if changed else speechSequence

	def _getRecentMessageTexts(self) -> list[str]:
		"""Return rendered Teams messages in accessibility-tree order."""
		try:
			foreground = api.getForegroundObject()
			windowHandle = foreground.windowHandle
			clientObject = UIAHandler.handler.clientObject
			rootElement = clientObject.elementFromHandle(windowHandle)
			groupCondition = clientObject.createPropertyCondition(
				UIAHandler.UIA_ControlTypePropertyId,
				UIAHandler.UIA_GroupControlTypeId,
			)
			elements = rootElement.findAll(
				UIAHandler.TreeScope_Descendants,
				groupCondition,
			)
		except Exception:
			log.debugWarning("Could not query Teams message groups", exc_info=True)
			return []

		messages = []
		try:
			elementCount = elements.length if elements is not None else 0
		except Exception:
			elementCount = 0
		for index in range(elementCount):
			try:
				element = elements.getElement(index).buildUpdatedCache(
					UIAHandler.handler.baseCacheRequest,
				)
				automationId = element.cachedAutomationId or ""
				if not automationId.startswith(_MESSAGE_AUTOMATION_ID_PREFIX):
					continue
				messageText = filterNavigationHelp(element.cachedName or "")
			except Exception:
				continue
			if messageText:
				messages.append(messageText)
		return messages

	def _presentRetrievedMessage(self, messageText: str) -> None:
		self._presentingRetrievedMessage = True
		try:
			ui.message(messageText)
		finally:
			self._presentingRetrievedMessage = False

	@scriptHandler.script(
		description="Reads a recent Teams chat message without moving focus",
		category="Microsoft Teams",
		gestures=_RECENT_MESSAGE_GESTURES,
	)
	def script_readRecentMessage(self, gesture):
		"""Read the numbered recent message, where 1 is the newest."""
		try:
			messageNumber = int(gesture.mainKeyName)
		except (AttributeError, TypeError, ValueError):
			return
		messages = self._getRecentMessageTexts()
		if messageNumber > len(messages):
			self._presentRetrievedMessage(f"Recent message {messageNumber} is not available")
			return
		self._presentRetrievedMessage(messages[-messageNumber])

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		try:
			isMessageRole = obj.role in (
				controlTypes.Role.GROUPING,
				controlTypes.Role.LISTITEM,
			)
		except Exception:
			isMessageRole = False
		containsHelp = False
		if not isMessageRole:
			for attribute in ("name", "description", "value"):
				try:
					if _containsNavigationHelp(getattr(obj, attribute, None)):
						containsHelp = True
						break
				except Exception:
					continue
		if isMessageRole or containsHelp:
			clsList.insert(0, TeamsMessageHelpFilterOverlay)

	def event_NVDAObject_init(self, obj):
		_filterObjectProperties(obj)

	def event_gainFocus(self, obj, nextHandler):
		_filterObjectProperties(obj)
		nextHandler()

	def event_UIA_notification(
		self,
		obj,
		nextHandler,
		notificationKind=None,
		notificationProcessing=None,
		displayString=None,
		activityId=None,
	):
		"""Clean transient UIA notification text for speech and braille."""
		if not _containsNavigationHelp(displayString):
			if (
				time.monotonic() <= self._suppressPunctuationNotificationUntil
				and _containsOnlyPunctuationOrSpacing(displayString)
			):
				self._suppressPunctuationNotificationUntil = 0.0
				return
			nextHandler()
			return
		self._suppressPunctuationNotificationUntil = (
			time.monotonic() + _PUNCTUATION_NOTIFICATION_GRACE_SECONDS
		)
		filtered = filterNavigationHelp(displayString)
		if filtered:
			ui.message(filtered)
