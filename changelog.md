# Changes

## 1.6.0

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
