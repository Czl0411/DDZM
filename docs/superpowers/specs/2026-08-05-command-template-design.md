# Command Reply Templates Design

## Goal

Let an administrator edit every reply produced by the existing group-game
commands without changing command names, permission checks, balances, daily
check-in rules, item data, or message delivery.

## Scope

- Add `/帮助` as a sixth built-in command.
- Store one editable template for each command outcome.
- Seed the current reply text as defaults, expressed with dynamic variables
  where a value already exists.
- Extend the existing **指令库** page to edit templates, insert allowed
  variables, save changes, and continue enabling or disabling commands.
- Use `Asia/Shanghai` for `{日期}`.

Out of scope: administrator-defined command names or command logic, random
reply selection, arbitrary expressions, user profile lookups, and changes to
the Socket.IO gateway.

## Data model

Add `command_reply_templates` with a composite unique key of `command` and
`scenario`. It stores `template` and Beijing timestamps. Migration seeding is
idempotent: it inserts missing defaults and never overwrites an existing
administrator edit.

Built-in command definitions gain `/帮助` with the description `查看当前可用指令`.

## Templates and variables

Each scenario exposes only the variables that are meaningful to it. Saving a
template containing another `{...}` token fails validation; plain braces not
matching a token are left untouched.

| Command | Scenario | Default template | Variables |
| --- | --- | --- | --- |
| `/入职` | `joined` | `{昵称}，欢迎入职摸鱼公司。当前余额：{余额} 摸鱼币。` | `{昵称}` `{余额}` `{日期}` |
| `/入职` | `already_joined` | `{昵称}已经在职，当前余额：{余额} 摸鱼币。` | `{昵称}` `{余额}` `{日期}` |
| `/入职` | `missing_name` | `请用 /入职 名字 加入摸鱼公司。` | `{日期}` |
| `/打卡` | `checked_in` | `打卡成功，领取 {打卡奖励} 摸鱼币。当前余额：{余额} 摸鱼币。` | `{昵称}` `{余额}` `{打卡奖励}` `{日期}` |
| `/打卡` | `already_checked_in` | `今天已经打过卡啦，明天再来。` | `{昵称}` `{日期}` |
| `/打卡` | `not_joined` | `请先用 /入职 名字 加入摸鱼公司。` | `{日期}` |
| `/余额` | `shown` | `{昵称}，当前余额：{余额} 摸鱼币。` | `{昵称}` `{余额}` `{日期}` |
| `/余额` | `not_joined` | `请先用 /入职 名字 加入摸鱼公司。` | `{日期}` |
| `/我的物品` | `shown` | `{昵称}的物品：\n{物品列表}` | `{昵称}` `{物品列表}` `{日期}` |
| `/我的物品` | `not_joined` | `请先用 /入职 名字 加入摸鱼公司。` | `{日期}` |
| `/商店` | `items_available` | `总监事小卖部：\n{商店列表}` | `{商店列表}` `{日期}` |
| `/商店` | `empty` | `总监事小卖部还没有上架商品。` | `{日期}` |
| `/帮助` | `shown` | `总监事指令簿：\n{指令列表}` | `{指令列表}` `{日期}` |

`{物品列表}` supplies `暂时空空如也。` when the employee owns no items.
`{指令列表}` renders only enabled built-in commands, each with its command and
description. `{日期}` renders the Beijing calendar date.

## Command handling

The command handler still parses only the six built-in command names and first
checks the existing enabled flag. It executes the current business operation,
selects its scenario, builds only that scenario's documented values, loads the
template, validates/render-substitutes the values, and enqueues the result.

An unavailable or malformed stored template must not break a valid game action:
the handler falls back to that scenario's seeded default and records no extra
business operation. The administrator API prevents malformed templates in
normal use; this fallback protects already-stored data.

## Admin API and UI

The core command-list response includes each command's description, enabled
state, and ordered template scenarios. A protected update endpoint accepts a
command, scenario, and template; it validates command/scenario membership,
maximum length, and the scenario variable whitelist.

The existing admin relay exposes the same list/update operations. The
**指令库** screen keeps its enable/disable button and adds one card per scenario:
scenario label, multiline editable template, allowed-variable buttons that
insert at the caret, and an explicit save button. Saved changes take effect on
the next received group message; no service restart is needed.

## Verification

- Repository and migration tests prove defaults seed once and preserve edits.
- Command tests cover every scenario, variable substitution, `/帮助`, disabled
  commands, invalid templates falling back, and Beijing date rendering.
- Core/admin API tests cover authorized template reads and validation failures.
- Admin UI tests cover template display, variable insertion, and save requests.
- Existing full test suite must pass before deployment; after deployment,
  update one template in the admin page and invoke its command once in the
  target group to verify the rendered reply.
