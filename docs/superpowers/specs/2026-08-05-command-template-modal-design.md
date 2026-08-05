# Command Template Modal Design

## Goal

Keep the command library compact by moving reply-template editing into a
single modal dialog.

## Scope

- Each template scenario shows a short current-template preview and an
  **编辑** button in the command library.
- Clicking **编辑** opens one modal for that command and scenario.
- The modal contains the editable multiline template, its allowed variable
  buttons, **取消**, and **保存**.
- Saving uses the existing protected template endpoint. On success, the modal
  closes, the command list reloads, and the existing success message appears.
- Cancelling, clicking the backdrop, or pressing Escape closes the modal
  without saving.

## Non-goals

This change does not modify template data, validation, command behavior,
variables, API contracts, or the command enable/disable control.

## Verification

- Static admin UI test asserts that the editor controls are rendered inside a
  modal and that save requests keep the existing endpoint and payload.
- Existing core and admin API tests remain unchanged and pass.
- Manual check: open one editor, insert a variable, save, and confirm the
  modal closes and the preview updates.
