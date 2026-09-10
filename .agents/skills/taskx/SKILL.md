---
name: taskx
description: Manage software-development work with taskx in Git repositories that use it for project tasks. Use when finding, creating, claiming, updating, releasing, or completing taskx-managed work; do not substitute Markdown task lists or raw Taskwarrior lifecycle commands.
---

# Taskx Workflow

Use `taskx` as the project task interface and Taskwarrior as storage behind it.
Run taskx commands from within the relevant Git repository so automatic project
scoping selects the correct task set.

## Design Records

Every implementation task must explicitly reference a committed design file.
Store designs under `design/` and use a portable UTC timestamp in each filename:

```text
design/YYYYMMDDTHHMMSSZ-short-kebab-topic.md
```

Keep the design focused on the intended outcome, relevant context, decisions,
constraints, and verification criteria. It is not a task-status checklist.
Several related tasks may share one design file.

Before starting the first related task:

1. Create the design file, or locate the design already named by the task.
2. Commit the design file before implementation begins. Stage it explicitly so
   unrelated working-tree changes are not included in the commit.
3. Include the exact `design/...` path in each new task's description. For an
   existing task that lacks the path, add it with a taskx note before claiming
   the work.

Do not start implementation while its design is uncommitted. If repository
policy or the current working-tree state prevents the required commit, report
the blocker instead of silently omitting the design commit.

## Start Work

1. Run `taskx help agent` if the local workflow or command surface is not already
   known in the current context.
2. Run `taskx ready --json` to find claimable work.
3. Select work that matches the user's request or current goal, then inspect it
   with `taskx show <uuid> --json`. Do not substitute an unrelated ready task
   merely because it appears first.
4. Run `taskx start <uuid>` before modifying files for that task.

If the requested implementation work has no existing task, first prepare and
commit its design, then create a concise task whose description includes the
design path, for example:

```bash
taskx add "Implement parser per design/20260910T083000Z-parser.md" --json
```

Start the returned UUID. Check `taskx list --json` first so an active, blocked,
waiting, or scheduled task is not duplicated.

Treat a successful `start` as the claim. If it reports a conflict, refresh the
task state and choose different work or explain the conflict; do not repeatedly
retry the claim.

## While Working

- Keep the claimed task aligned with the work being performed.
- Record durable, task-specific findings with
  `taskx note <uuid> "<text>"` when they will help the next worker.
- Create a separate task for newly discovered, independently actionable work.
  Use `taskx depends <uuid> add <dependency-uuid>` only when the first task
  genuinely cannot complete until the second does.
- Use UUIDs or unambiguous UUID prefixes from taskx output. Prefer `--json` when
  consuming task data programmatically.
- Do not use raw `task` commands to bypass taskx's project scope, attribution,
  locking, or lifecycle checks.
- Do not maintain a parallel task list in Markdown.

## Finish or Hand Back Work

After the requested result is complete and appropriately verified, immediately
run `taskx done <uuid>`. Do not mark a task done merely because work stopped or
because only part of its acceptance criteria passed.

After completing the last unfinished task that references a design file, remove
that design file and commit its deletion. Use `taskx list --json` to confirm no
unfinished task still names the exact path before removing it. The Git history
retains the design while the working tree stays focused on live work.

If the work must be abandoned or postponed after it was started, run:

```bash
taskx release <uuid> --reason "<concise reason and useful next step>"
```

Release rather than leaving a stale active claim. A released task must be
started again before it can be completed.

## Working-Set Boundaries

- `taskx ready --json` is the claimable queue.
- `taskx list --json` is the complete unfinished project working set, including
  blocked, waiting, scheduled, and active tasks.
- Do not inspect completed tasks unless the user explicitly requires historical
  investigation.
- Let taskx detect the Git project and current actor. Use `taskx project` or
  `taskx actor` only to diagnose unexpected scoping or attribution.

If taskx is unavailable or the directory is not a taskx-compatible Git project,
report that condition instead of silently switching to a different task tracker.

When reporting the result to the user, include the task UUID and whether it was
completed or released if that status is useful to the handoff.
