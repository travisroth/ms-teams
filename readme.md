# Microsoft Teams Accessibility Enhancements for NVDA

This add-on improves access to the New Microsoft Teams desktop client
(`ms-teams.exe`). It filters the repetitive instruction beginning with:

> Press Enter to explore message content

It also provides commands for reviewing recent chat messages without moving
keyboard focus.

## Recent-message commands

- Ctrl+Shift+1: newest rendered message.
- Ctrl+Shift+2: second-newest rendered message.
- Continue through Ctrl+Shift+9 for the ninth-newest rendered message.

The selected message is presented with `ui.message()` for speech and braille.
Teams virtualizes older content, so a message outside the current accessibility
tree is reported as unavailable. These gestures override Teams' own
Ctrl+Shift+number app-switching shortcuts while this AppModule is active.

## Navigation-help filtering

- Cleans the accessible `name`, `description`, and `value` of Teams message
  objects.
- Filters late-added speech sequences and UI Automation notifications.
- Intercepts `BrailleHandler.message` before NVDA switches to its secondary
  `messageBuffer`, preventing instruction-only messages from causing a flash.
- Suppresses punctuation left behind by the removed instruction, including a
  period sent as a separate immediate UIA notification.
- Retains a final braille-buffer filter as fallback coverage.

## Compatibility

- Minimum NVDA version: 2024.1
- Last tested NVDA version: 2026.1.1
- Application: New Microsoft Teams (`ms-teams.exe`)

## Installation

1. Open the `.nvda-addon` file.
2. Approve installation or the update in NVDA.
3. Restart NVDA when prompted.

## Manual test

1. Open a chat in the New Microsoft Teams desktop client.
2. Move focus into a message with Tab or Shift+Tab.
3. Confirm the message is announced without the repetitive navigation help.
4. Repeat with a braille display and confirm there is no help-text or period
   flash.
5. Leave focus in the message editor and press Ctrl+Shift+1, then
   Ctrl+Shift+2. Confirm the newest and second-newest rendered messages are
   presented without moving focus.
6. Confirm Enter still explores a message and Escape still exits it; the add-on
   changes output only.

If the add-on does not activate, press NVDA+F1 on a Teams message and verify
that the AppModule shown in Developer Information is `ms_teams`.

## License

GNU General Public License, version 2 or later. See [COPYING.txt](COPYING.txt).
