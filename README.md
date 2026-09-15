# taskx

`taskx` is a small project-aware command-line interface for managing
project-specific development tasks through
[Taskwarrior](https://taskwarrior.org/). It is designed for projects built
with AI coding agents, while remaining convenient for direct human use.

Taskwarrior stays the canonical task store. taskx adds automatic Git project
scoping, explicit lifecycle transitions, and automatic actor attribution.
This document describes the initial v0.1 command surface, which follows
`initial_design.md` in this repository.

## Requirements

- Python >= 3.11
- `git`
- Taskwarrior 3.x (verified against Taskwarrior 3.5)

taskx uses [Typer](https://typer.tiangolo.com/) for its typed, documented command
line interface and Rich terminal help.

## Installation

From a checked-out repository, install with any uv/pip-compatible tool; v0.1
is not on PyPI yet:

```bash
uv tool install .
# or
pipx install .
```

Both tools also accept a `git+https://...` repository URL in place of `.`.

## Project scoping

taskx derives the Taskwarrior project from the Git repository containing the
current directory (`git rev-parse --show-toplevel`) and uses the repository
root basename with Taskwarrior's exact `project.is:<name>` filter.
Hierarchical subprojects do not leak into results, the user's active
Taskwarrior context is disabled for every invocation, and taskx fails with a
clear error when run outside a Git repository.

## Commands

| Command | Purpose |
| ------------------------------------------ | ---------------------------------------- |
| `taskx ready [--json]` | Tasks a new worker may claim |
| `taskx list [--json]` | All unfinished tasks, including waiting |
| `taskx show <uuid> [--json]` | One task with full metadata |
| `taskx add <description> [--depends <uuid>]` | Create a task |
| `taskx start <uuid> [--json]` | Claim a task |
| `taskx release <uuid> [--reason text]` | Stop without completing |
| `taskx done <uuid> [--json]` | Complete a started task |
| `taskx note <uuid> <text>` | Add an annotation |
| `taskx depends <uuid> add\|remove <uuid>` | Manage dependencies |
| `taskx actor` | Print the detected actor |
| `taskx project` | Print the detected project |
| `taskx skill install codex\|claude\|opencode [--global]` | Install the taskx agent skill |
| `taskx help agent` | Machine-oriented workflow summary |

Every task command also accepts `--json`.

Tasks are referenced by Taskwarrior UUIDs; unique UUID prefixes are accepted
where they resolve unambiguously. `ready` excludes active, blocked, waiting,
and future-scheduled tasks. `list` shows the unfinished working set and never
includes completed or deleted tasks.

## Lifecycle

```text
pending ──start──► active ──done──► completed
                      │
                      └──release──► pending
```

- `start` refuses an already-active task, so two agents cannot silently
  claim the same work.
- `done` requires an active task that was started through taskx; a released
  task must be started again before completion.
- Every `add`, `start`, and `done` records the current actor in the
  `taskx_created_by`, `taskx_started_by`, and `taskx_closed_by` Taskwarrior
  UDAs. `release` retains `taskx_started_by` as history.

## JSON output

`--json` prints a stable, normalized representation. Fields are fixed:
`uuid`, `description`, `project`, `status`, `active`, `blocked`, `waiting`,
`depends`, `annotations`, `entry`, `start`, `end`, `wait`, `scheduled`,
`created_by`, `started_by`, and `closed_by`. Taskwarrior numeric IDs never
appear in the JSON interface.

```json
{
  "uuid": "80b65cb1-5fd2-4efa-b4a8-ebe17346b69c",
  "description": "Implement evaluator",
  "project": "wirecat",
  "status": "pending",
  "active": false,
  "blocked": false,
  "waiting": false,
  "depends": ["352fc723-4178-4775-a05a-cb7c6f28ac51"],
  "annotations": [],
  "entry": "20260910T060000Z",
  "start": null,
  "end": null,
  "wait": null,
  "scheduled": null,
  "created_by": "human:juan",
  "started_by": null,
  "closed_by": null
}
```

## Actor detection

taskx determines the current actor automatically, in precedence order:

1. `TASKX_ACTOR`, an explicit override that always wins;
2. known Codex, Claude Code, and OpenCode session environment variables;
3. `human:<username>` from the local user name.

Empty environment values are ignored. AI harnesses should set `TASKX_ACTOR`
to guarantee attribution, and `taskx actor` prints the resolved identity for
debugging.

## Errors and exit codes

Expected failures print `error: <message>` on stderr without a traceback.

| Exit code | Meaning |
| --------- | ---------------------------------------------------- |
| 0 | success |
| 1 | general taskx error |
| 2 | usage error (bad arguments, ambiguous UUID prefix) |
| 3 | task not found |
| 4 | conflict (for example, task already active) |

## Concurrency

Mutating commands (`add`, `start`, `release`, `done`, `note`, `depends`) run
under a lightweight process lock that encloses validation, mutation, and
postcondition verification, so concurrent taskx agents cannot interleave a
claim. The lock serializes taskx only; it cannot protect direct concurrent
Taskwarrior use.

## Development

The flake provides the development toolchain and system executables (Python
3.11, uv, Ruff, ty, Taskwarrior, Git); uv owns Python dependencies and the
lockfile. No Nix package derivation is produced.

```bash
nix develop # toolchain shell
uv sync # create or refresh the environment
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

## Agent integration

Install the bundled task-management skill for the coding agent used in the
current repository:

```bash
taskx skill install codex
taskx skill install claude
taskx skill install opencode
```

Local installation is the default and writes beneath the Git root to
`.agents/skills/taskx`, `.claude/skills/taskx`, or
`.opencode/skills/taskx`, respectively. Add `--global` after the agent name to
install for the current user instead:

```bash
taskx skill install codex --global
```

The global destinations are `~/.agents/skills/taskx`,
`~/.claude/skills/taskx`, and `~/.config/opencode/skills/taskx`. Reinstalling
identical content is safe; taskx refuses to overwrite a different existing
skill.

Without the skill, a repository using taskx needs only a minimal `AGENTS.md`:

```md
## Tasks

Use `taskx` for project task management.

Run `taskx help agent` before managing tasks.

Do not create or maintain Markdown task lists.
```

The full workflow is built into the tool: `taskx help agent`.
