# Microsoft Teams Accessibility Enhancements for NVDA
# Copyright (C) 2026 Ryan Praeuner and contributors
# SPDX-License-Identifier: GPL-2.0-or-later
# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

"""Improve message navigation and presentation in the New Microsoft Teams client."""

from __future__ import annotations

import re
import time
import traceback
from typing import Optional, Sequence, TypeGuard
import unicodedata

import api
import appModuleHandler
import braille
from logHandler import log
from NVDAObjects import NVDAObject
import scriptHandler
import ui
import UIAHandler

try:
	from speech.extensions import filter_speechSequence
except (ImportError, AttributeError):
	filter_speechSequence = None


#: Cheap substring that must be present before the full pattern can match.
#: Property getters run for every object in Teams, so avoid the regex where possible.
_NAVIGATION_HELP_HINT = "explore"

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

#: Whole announcements from Teams live regions that carry no useful information.
#: These are matched against the complete announcement, never against object
#: names, so an object legitimately called "7 results" is left alone.
#: Add further Teams noise here.
_SUPPRESSED_ANNOUNCEMENT_PATTERNS = (
	# The chat list re-renders whenever a message arrives and its status region
	# re-announces the filter count, even though the user never filtered anything.
	re.compile(r"^\s*(?:\d+|no)\s+results?\s*$", re.IGNORECASE),
	# Send progress. Pressing Enter is its own confirmation, and a failure to send
	# is reported separately, so these two carry nothing the user does not know.
	re.compile(r"^\s*(?:sending|message\s+sent|sent)[\s.…!]*$", re.IGNORECASE),
)


_PUNCTUATION_NOTIFICATION_GRACE_SECONDS = 0.75
_MESSAGE_AUTOMATION_ID_PREFIX = "message-body-"
_RECENT_MESSAGE_GESTURES = tuple(f"kb:control+shift+{number}" for number in range(1, 10))

#: Object properties that NVDA renders into a braille region, and that Teams
#: could plausibly hang its navigation help off.
_FILTERED_PROPERTIES = (
	"name",
	"description",
	"value",
	"placeholder",
	"errorMessage",
)

#: Raw UIA properties, safe to read without populating NVDA's property cache
#: with filtered values.
_RAW_UIA_PROPERTIES = ("UIAFullDescription", "UIAHelpText")

#: Extra properties worth showing in the diagnostic dump but not worth filtering.
_DIAGNOSTIC_PROPERTIES = (
	_FILTERED_PROPERTIES
	+ (
		"role",
		"keyboardShortcut",
		"roleTextBraille",
	)
	+ _RAW_UIA_PROPERTIES
)


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


def _mightContainNavigationHelp(text: object) -> TypeGuard[str]:
	"""Cheap check that also narrows ``text`` to ``str`` for the caller."""
	return isinstance(text, str) and _NAVIGATION_HELP_HINT in text.lower()


def filterNavigationHelp(text: Optional[str]) -> Optional[str]:
	"""Remove the Teams message-navigation instruction from ``text``."""
	if not _mightContainNavigationHelp(text):
		return text
	if _NAVIGATION_HELP_RE.search(text) is None:
		return text
	filtered = _NAVIGATION_HELP_RE.sub("", text)
	filtered = re.sub(r"[ \t]{2,}", " ", filtered)
	filtered = re.sub(r"[ \t]*\n[ \t]*", "\n", filtered)
	filtered = filtered.strip()
	if _containsOnlyPunctuationOrSpacing(filtered):
		return ""
	return filtered


def isSuppressedAnnouncement(text: object) -> bool:
	"""Is this entire announcement Teams noise that should never be presented?"""
	return isinstance(text, str) and any(
		pattern.match(text) is not None for pattern in _SUPPRESSED_ANNOUNCEMENT_PATTERNS
	)


def _containsNavigationHelp(text: object) -> bool:
	return _mightContainNavigationHelp(text) and _NAVIGATION_HELP_RE.search(text) is not None


class TeamsMessageHelpFilterOverlay(NVDAObject):
	"""Strip the Teams navigation help from the properties NVDA presents.

	Speech and braille both build their output from the NVDAObject, so filtering
	here removes the help from every output channel at once, including the
	braille re-render that Teams triggers a few seconds after focus when it
	finally attaches its help text to the focused object.

	This must derive from L{NVDAObject} so that NVDA's auto property metaclass
	turns these ``_get_`` methods into real properties. A plain mixin class with
	no NVDA base is silently ignored when NVDA builds the dynamic overlay class,
	because that class is created with an empty namespace and the metaclass only
	generates properties from the namespace it is given.
	"""

	def _get_name(self):
		return filterNavigationHelp(super()._get_name())

	def _get_description(self):
		return filterNavigationHelp(super()._get_description())

	def _get_value(self):
		return filterNavigationHelp(super()._get_value())

	def _get_placeholder(self):
		return filterNavigationHelp(super()._get_placeholder())

	def _get_errorMessage(self):
		return filterNavigationHelp(super()._get_errorMessage())


class AppModule(appModuleHandler.AppModule):
	"""NVDA support for ``ms-teams.exe`` (New Microsoft Teams)."""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._speechFilterRegistered = False
		self._suppressPunctuationNotificationUntil = 0.0
		self._presentingRetrievedMessage = False
		self._traceEvents = False
		self._originalBrailleMessage = None
		self._brailleMessageFilter = None
		if filter_speechSequence is not None:
			filter_speechSequence.register(self._filterSpeechSequence)
			self._speechFilterRegistered = True
		self._installBrailleMessageFilter()

	def terminate(self):
		self._removeBrailleMessageFilter()
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
		"""Catch Teams help that reaches speech from outside the object properties."""
		if self._presentingRetrievedMessage or not self._isThisTeamsInstanceFocused():
			return speechSequence
		# Live regions reach speech as a bare speakText, so the whole sequence is
		# the announcement. Focus reports always carry role and state text too,
		# which is why this cannot silence a real object called "7 results".
		spokenText = "".join(item for item in speechSequence if isinstance(item, str))
		if isSuppressedAnnouncement(spokenText):
			return []
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
		"""Return rendered Teams messages in accessibility tree order."""
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
			ui.message(f"Recent message {messageNumber} is not available")
			return
		ui.message(messages[-messageNumber])

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		# Applied unconditionally. Teams adds the help text asynchronously, so it
		# is often absent when the object is first created. Deliberately do not
		# read obj.name/description/value here either: doing so caches the
		# unfiltered values for this core cycle before the overlay is in place.
		clsList.insert(0, TeamsMessageHelpFilterOverlay)

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
		if self._traceEvents:
			self._logTracedEvent(
				"UIA_notification",
				obj,
				{
					"notificationKind": notificationKind,
					"notificationProcessing": notificationProcessing,
					"displayString": displayString,
					"activityId": activityId,
				},
			)
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

	# Diagnostics. These exist to identify which NVDA path Teams uses to deliver
	# its delayed help text, and can be removed once that is settled.

	def __getattr__(self, name: str):
		"""Provide a tracing handler for any event this module does not define.

		Only consulted when normal attribute lookup fails, so the real handlers
		above still take precedence, and only active while tracing is on.
		"""
		if not name.startswith("event_"):
			raise AttributeError(name)
		# Read from __dict__ directly: going through self would re-enter here.
		if not self.__dict__.get("_traceEvents"):
			raise AttributeError(name)
		eventName = name[len("event_") :]

		def tracedEvent(obj, nextHandler=None, *args, **kwargs):
			# Not every event is dispatched with a nextHandler.
			# event_NVDAObject_init, for one, is called with the object alone.
			self._logTracedEvent(eventName, obj, kwargs)
			if callable(nextHandler):
				return nextHandler()

		return tracedEvent

	@staticmethod
	def _rawName(obj) -> Optional[str]:
		"""Return the object's name as it is before this add-on filters it.

		Walks past the overlay in the MRO and calls the underlying getter
		directly, so nothing is written to NVDA's property cache.
		"""
		for cls in type(obj).__mro__:
			if cls is TeamsMessageHelpFilterOverlay:
				continue
			getter = cls.__dict__.get("_get_name")
			if getter is not None:
				try:
					return getter(obj)
				except Exception as error:
					return f"<error: {error}>"
		return None

	def _installBrailleMessageFilter(self) -> None:
		"""Filter Teams help out of braille flash messages.

		Chromium live regions reach NVDA through
		``nvdaControllerInternal_reportLiveRegion``, which queues
		``speech.speakText`` and ``braille.handler.message`` with a raw string.
		No NVDAObject is involved, so the overlay cannot see this text, and NVDA
		offers no braille counterpart to ``filter_speechSequence``. Wrapping the
		handler instance is the only point where the string still exists.

		This sets an attribute on the handler object, never on
		``BrailleHandler`` itself, so other applications and other add-ons are
		untouched, and it is removed again in ``terminate``.
		"""
		handler = braille.handler
		if handler is None:
			log.debugWarning("Braille handler not available, Teams braille filter not installed")
			return
		if self._brailleMessageFilter is not None:
			return
		originalMessage = handler.message
		self._originalBrailleMessage = originalMessage

		def filteredBrailleMessage(text, *args, **kwargs):
			if self._traceEvents:
				self._logBrailleMessage(text)
			if self._shouldFilterBrailleMessage():
				if isSuppressedAnnouncement(text):
					return
				filtered = filterNavigationHelp(text)
				if not filtered:
					return
				text = filtered
			return originalMessage(text, *args, **kwargs)

		self._brailleMessageFilter = filteredBrailleMessage
		handler.message = filteredBrailleMessage

	def _removeBrailleMessageFilter(self) -> None:
		handler = braille.handler
		if handler is not None and self._brailleMessageFilter is not None:
			if handler.message is self._brailleMessageFilter:
				# Deleting the instance attribute exposes the class method again.
				try:
					del handler.message
				except AttributeError:
					pass
			else:
				# Another Teams process wrapped it after us. Unwinding out of order
				# would discard their filter, so leave ours in the chain. It goes
				# inert anyway, since its focus check can no longer match.
				log.debugWarning("Teams braille filter was wrapped by another instance, leaving it in place")
		self._brailleMessageFilter = None
		self._originalBrailleMessage = None

	def _shouldFilterBrailleMessage(self) -> bool:
		return not self._presentingRetrievedMessage and self._isThisTeamsInstanceFocused()

	def _logBrailleMessage(self, text) -> None:
		"""Diagnostic: log the text and call site of a braille flash message."""
		try:
			callSite = "".join(traceback.format_stack()[-14:-1])
			log.info(
				f"Teams braille message: text={text!r}"
				f" containsHelpText={_containsNavigationHelp(text)}"
				f"{chr(10)}call site:{chr(10)}{callSite}",
			)
		except Exception:
			log.debugWarning("Could not log a braille message", exc_info=True)

	def _describeObject(self, obj, rawOnly: bool = False) -> str:
		"""Describe obj for the log.

		:param rawOnly: only read raw UIA properties. Reading NVDA properties
			populates the object's property cache with filtered values, which
			would mask the very problem the event trace is trying to catch.
		"""
		if obj is None:
			return "None"
		parts = [
			f"class={type(obj).__name__}",
			f"overlayApplied={isinstance(obj, TeamsMessageHelpFilterOverlay)}",
		]
		propertyNames = _RAW_UIA_PROPERTIES if rawOnly else _DIAGNOSTIC_PROPERTIES
		for propertyName in propertyNames:
			try:
				value = getattr(obj, propertyName, None)
			except Exception as error:
				value = f"<error: {error}>"
			if value in (None, ""):
				continue
			parts.append(f"{propertyName}={value!r}")
		return ", ".join(parts)

	def _logTracedEvent(self, eventName: str, obj, kwargs) -> None:
		try:
			carriesHelp = any(_containsNavigationHelp(value) for value in kwargs.values()) or any(
				_containsNavigationHelp(getattr(obj, propertyName, None))
				for propertyName in _RAW_UIA_PROPERTIES
			)
			rawName = self._rawName(obj)
			carriesHelp = carriesHelp or _containsNavigationHelp(rawName)
			log.info(
				f"Teams event trace: {eventName}"
				f" carriesHelpText={carriesHelp}"
				f" rawName={rawName!r}"
				f" kwargs={kwargs!r}"
				f" obj: {self._describeObject(obj, rawOnly=True)}",
			)
		except Exception:
			log.debugWarning("Could not trace a Teams event", exc_info=True)

	@scriptHandler.script(
		description="Toggles logging of Microsoft Teams accessibility events",
		category="Microsoft Teams",
		gestures=["kb:NVDA+control+shift+e"],
	)
	def script_toggleEventTrace(self, gesture):
		self._traceEvents = not self._traceEvents
		ui.message(
			"Teams event tracing on" if self._traceEvents else "Teams event tracing off",
		)

	@scriptHandler.script(
		description="Logs what is currently on the braille display in Microsoft Teams",
		category="Microsoft Teams",
		gestures=["kb:NVDA+control+shift+d"],
	)
	def script_logBrailleState(self, gesture):
		handler = braille.handler
		if handler is None:
			ui.message("Braille is not running")
			return
		isMessage = handler.buffer is handler.messageBuffer
		lines = [
			"Teams braille diagnostic",
			"Active buffer: "
			+ (
				"messageBuffer, so this came from ui.message or braille.handler.message"
				if isMessage
				else "mainBuffer, so this is the focus or review region"
			),
		]
		for index, region in enumerate(handler.buffer.regions):
			rawText = getattr(region, "rawText", None)
			lines.append(f"region {index}: {type(region).__name__} rawText={rawText!r}")
			lines.append(f"region {index} object: {self._describeObject(getattr(region, 'obj', None))}")
		lines.append(f"focus: {self._describeObject(api.getFocusObject())}")
		log.info("\n".join(lines))
		ui.message(
			"Braille diagnostic written to the log, " + ("flash message" if isMessage else "focus region"),
		)
