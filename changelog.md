# Changes

## 1.6.0

- Chat messages are now reported as list items rather than groupings, which
  also removes the role text from speech and the role abbreviation from braille,
  because `LISTITEM` is a silent role on focus.
- Chat messages are read from their own properties rather than their
  IAccessible2 text, so "report current line" reads the message instead of a
  blank. Chromium exposes IAccessibleText on the message element, but its own
  text is a single space, because the content sits in child nodes and the name
  comes from a related element.
- The chat history container declares a flow run for the BrlMultiline add-on and
  supplies the newest message as the starting point, so the history can be
  pinned to a display or segment while focus is elsewhere.
- Chat messages declare a flow run for the BrlMultiline add-on, so a multi-row
  braille display can show a run of messages at once. Nothing is imported from
  BrlMultiline and the add-on behaves identically without it.

- Removed the global plugin entirely. The app module is named `ms-teams.py`
  after the executable, so NVDA loads it without any registration.
- Removed all monkey patching of `BrailleHandler.update` and of the
  `BrailleHandler` class.
- Fixed the overlay class, which previously had no NVDA base class and so was
  silently ignored when NVDA built the dynamic overlay type. It now filters
  `name`, `description`, `value`, `placeholder`, and `errorMessage`.
- Filters Chromium live region announcements where they enter NVDA: through
  `filter_speechSequence` for speech, and through a wrapper on the braille
  handler instance for braille.
- Suppresses the chat list filter count, such as "7 results", which Teams
  re-announced on every incoming message.
- Suppresses "Sending" and "Message sent". Send failures are still announced.
- Added NVDA+Control+Shift+E event tracing and NVDA+Control+Shift+D braille
  state logging as diagnostics.
- Fixed a crash in the recent-message command when a message was unavailable.

## 1.5.0

- Migrated the project to the official NVDA add-on template.
- Filters the repetitive Teams message-navigation instruction from speech and
  braille.
- Prevents instruction-only and punctuation-only notifications from flashing
  NVDA's braille `messageBuffer`.
- Adds Ctrl+Shift+1 through Ctrl+Shift+9 to read recent rendered chat messages
  without moving focus.
