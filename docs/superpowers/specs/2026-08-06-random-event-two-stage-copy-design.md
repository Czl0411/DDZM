# Random Event Two-Stage Copy Design

## Goal

Make each random-event scene use a separate sign-up announcement and a
randomly selected formal role-play opening, while keeping `/加入` reusable for
future games and preventing non-participants from breaking an active scene.

## Scope

This change affects only the existing random-event game and its management
screen. It does not add another game type, permit more than one joinable game,
or change random-event scheduling, rewards, or settlement.

## Scene Configuration

Every scene has the following independently configurable content:

- **Sign-up announcement**: one required message sent when the scheduled event
  enters the sign-up state. It can name the scene and invite players to use
  `/加入 角色`.
- **Role seats**: the selectable player identities and capacities. For example,
  a `主持` seat is selected with `/加入 主持`.
- **Formal role-play openings**: one or more required messages. When all seats
  are full, the service randomly selects one enabled opening and sends it as
  the start of the role-play.

The management modal presents these as separate fields: basic scene data and
sign-up announcement, seat rows, and a repeatable formal-opening list. A scene
cannot be enabled without at least one non-empty formal role-play opening.

## Event Lifecycle

1. A scheduled event starts and sends the configured sign-up announcement.
2. Players join its role seats through the common `/加入 角色` command.
3. When every seat is full, the service chooses one formal role-play opening,
   stores it on that event record, and sends it once with the event-start
   notice.
4. Joined players can role-play normally; their non-command messages count
   toward their individual round totals.
5. The selected opening stays fixed for that event, including across restarts.

The currently stored single `opening_text` value is migrated as the scene's
sign-up announcement. Existing scenes receive one formal opening copied from
that value, so existing data remains valid and no configured scene becomes
unstartable after deployment.

## Common `/加入` Routing

`/加入` remains a common game command. The group permits only one joinable
game at a time, so the command routes to that active game's join handler. For
the current random event, the argument remains the selected role identity.
No game name is required and no multi-game disambiguation is added.

## Non-Participant Speech Rule

While a random event is `in_progress`, ordinary messages from users who are
not active participants must be entirely wrapped in either Chinese full-width
parentheses (`（内容）`) or ASCII parentheses (`(内容)`). Whitespace is ignored
for this check, but any non-whitespace text outside the matching outer
parentheses makes the message invalid. The wrapped content must contain at
least one non-whitespace character.

Invalid non-participant ordinary messages receive a fixed warning reply and do
not count as role-play rounds. Commands are excluded from this validation.
The restriction ends as soon as the event ends, and does not affect ordinary
group chat outside an active random event.

## Data and API Changes

- Rename the current scene/event `opening_text` concept to a sign-up text.
- Add a child table for formal scene openings, allowing multiple rows per
  scene.
- Add a frozen selected formal-opening field to each event record.
- Extend scene create, update, and list API payloads with `signup_text` and
  `openings`.
- Preserve existing admin concurrency and idempotency behavior for scene
  mutations.

## Verification

Automated tests must prove that:

- creating a scene requires a sign-up announcement and at least one formal
  opening;
- sign-up uses the announcement, while a full event sends one stored formal
  opening;
- `/加入 角色` keeps joining the sole active random event;
- participant messages count rounds, while valid parenthesized observer
  messages do not count and invalid observer messages produce a warning;
- the management API and static UI submit and render the split scene fields.
