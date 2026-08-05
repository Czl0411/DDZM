# Command Template Modal Design

## Goal

Keep the command library compact by moving all reply-template scenario details
and editing into a single modal dialog.

## Scope

- Each command shows only its name, description, enable/disable control, and
  one **配置回复** button in the command library.
- Clicking **配置回复** opens one modal for that command.
- The modal contains a scenario selector, the selected scenario's multiline
  template, its allowed variable buttons, **取消**, and **保存**.
- Saving uses the existing protected template endpoint. On success, the modal
  closes, the command list reloads, and the existing success message appears.
- Cancelling, clicking the backdrop, or pressing Escape closes the modal
  without saving.

## Non-goals

This change does not modify template data, validation, command behavior,
variables, API contracts, or the command enable/disable control.

## Verification

- Static admin UI test asserts that the command page exposes only the command
  editor trigger while the scenario selector and editor controls are rendered
  inside the modal. Save requests keep the existing endpoint and payload.
- Existing core and admin API tests remain unchanged and pass.
- Manual check: open one editor, insert a variable, save, and confirm the
  modal closes and the preview updates.
