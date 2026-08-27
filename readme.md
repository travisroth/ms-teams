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
tree is reported as unavailable. Note: these gestures override Teams' own
Ctrl+Shift+number app-switching shortcuts in web browser view while this AppModule is active. This appModule is intended for the Windows client and not tested in web view.

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

## Messages as list items

Teams gives each message in the chat history a role of grouping. The messages
already arrow and take focus like a list, but nothing tells NVDA that, so every
message was announced as "grouping" and carried a role abbreviation on braille.

They are now reported as list items. `LISTITEM` is in
`controlTypes.silentRolesOnFocus`, which both `speech.speakObject` and
`getPropertiesBraille` honour by dropping the role text for an object that has a
name, so the correct role also removes that noise from both outputs.

## Multi-line braille

The message objects declare a flow run for the BrlMultiline add-on, which fills
a multi-row braille display with a run of objects: on a display with eight rows,
eight messages under the fingers at once rather than one at a time.

This add-on imports nothing from BrlMultiline and does not depend on it. The
declaration is a class attribute and two traversal methods that nothing in NVDA
reads, so the module behaves identically when BrlMultiline is absent.

The chat history container declares itself too, so the history can be pinned to
a display or segment and stay under the fingers while focus is elsewhere. It
supplies its own starting point, the newest message, because BrlMultiline would
otherwise start at the first member, which is right for a list and wrong for a
chat. A reader already on a message always wins over that, so it only decides
where a pin made from elsewhere begins.

The traversal is bounded. Messages are not siblings of each other, so a step
climbs to the wrapper, moves to its next or previous sibling, then descends to
the message it holds. Wrappers holding no message, such as timestamps and the
emoji pop-over Teams inserts beside a focused message, are skipped within a
limit, so a gap does not end the run and a long stretch cannot turn one pan into
a scan of the loaded history. The walk stops at the ends rather than wrapping,
and never moves focus.

## Diagnostics

Two commands help identify where unwanted output originates.

- NVDA+Control+Shift+E toggles event tracing. While it is on, every event
  reaching the app module and every braille flash message is written to the
  NVDA log with its text and call site, including messages the add-on
  suppresses.
- NVDA+Control+Shift+F logs the chat flow run: the container, the last few
  wrappers at the end of the history, a walk forward and back from the newest
  message, and what the message held since the previous press now reports as
  its next. That last part is the question a pinned monitor asks, so pressing it
  once, waiting for a new message, then pressing it again shows whether a
  retained message object can still see what arrived after it.
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
