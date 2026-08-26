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

## Noise filtering

Teams sends the same repetitive text through two completely different NVDA
paths, so the add-on filters each one at its source.

Focused objects. Teams attaches its navigation help to the focused message,
sometimes seconds after the focus event. An overlay class filters `name`,
`description`, `value`, `placeholder`, and `errorMessage`, which covers speech,
braille, object navigation, and browse mode control fields at once, because they
all read the same NVDAObject properties.

Chromium live regions. Teams also announces through ARIA live regions. These
reach NVDA through `nvdaControllerInternal_reportLiveRegion`, which queues
`speech.speakText` and `braille.handler.message` with a raw string. No
NVDAObject is involved, so no overlay or event handler can see them. Speech is
filtered through `speech.extensions.filter_speechSequence`. NVDA has no braille
equivalent of that extension point, so the add-on wraps `message` on the braille
handler instance, never on the `BrailleHandler` class, guarded by a focus check
and removed again in `terminate`.

Announcements suppressed in full:

- The navigation help beginning "Press Enter to explore message content".
- The chat list filter count, such as "7 results", which Teams re-announces
  every time the list re-renders for an incoming message.
- Send progress, "Sending" and "Message sent". Failures such as "Message not
  sent" are still announced.

Incoming message announcements are never touched.

## Diagnostics

Two commands help identify where unwanted output originates.

- NVDA+Control+Shift+E toggles event tracing. While it is on, every event
  reaching the app module and every braille flash message is written to the
  NVDA log with its text and call site, including messages the add-on
  suppresses.
- NVDA+Control+Shift+D logs the current braille state: which buffer is active,
  the regions it holds, and the properties of the focused object.

## Compatibility

- Minimum NVDA version: 2026.1
- Last tested NVDA version: 2026.3
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
that the AppModule shown in Developer Information is `ms-teams`.

## License

GNU General Public License, version 2 or later. See [COPYING.txt](COPYING.txt).
