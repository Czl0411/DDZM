# Random Event Role Variable Design

## Goal

Allow formal random-event openings to refer to configured seat identities and
show the real display names of the players who selected those identities.

## Scope

This applies only to a scene's formal role-play openings. It does not change
the scene sign-up announcement, `/加入 角色` syntax, rewards, round counting, or
observer speech rule.

## Variable Syntax and Rendering

A formal opening may contain a seat-role variable written exactly as `{角色名}`.
The role name is the one configured in the scene's seat list.

For example, a scene with the seats `主持` and `员工` can use:

```text
{主持}端着咖啡走进茶水间，对{员工}说……
```

When all seats are full, the system replaces each variable with the display
name of the player who joined that role, then sends the rendered result as the
formal opening. If a role has multiple seats, its names are ordered by join
time and joined with `、`, for example `小明、小红`.

The system chooses one formal-opening template at random when sign-up begins.
When the event becomes full, it renders that chosen template, replaces the
event's stored formal-opening text with the rendered result, and sends it.
Thus the delivered text is stable and remains available on the event record.

## Validation

Each braced variable token in a formal opening must name a role in the same
scene's submitted seat list. Saving a scene with an unknown variable is
rejected with a clear validation message. Braces with no content are ordinary
text and are not treated as a variable.

## Management Screen

Each formal-opening textarea has an **insert role variable** row. Its buttons
are generated from the currently entered seat-role rows. Clicking a button
inserts its `{角色名}` token at the focused textarea cursor; if that textarea
has not received focus, the token is appended to that opening.

Changing a seat role immediately refreshes the available variable buttons.
The editor remains entirely inside the existing scene modal.

## Verification

Automated tests cover:

- rendering one player per role into a selected formal opening;
- joining multiple players to one role and rendering their names in join order;
- rejecting a formal opening that references an unknown role;
- rendering and inserting the current role-variable chips in the scene modal.
