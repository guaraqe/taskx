# taskx

taskx is a project-aware command-line interface for managing development
tasks, backed by [Taskwarrior](https://taskwarrior.org/). Every task is
scoped to the Git repository you run it from, so tasks never leak between
projects. Tasks move through an explicit lifecycle (`pending → active →
completed`) with claim semantics, so two workers cannot silently grab the
same task.

Taskwarrior remains the canonical task store; taskx just scopes it, adds
lifecycle transitions, and records who did what.

## Installation

```bash
nix profile install github:guaraqe/taskx#taskx
```

or run it without installing:

```bash
nix run github:guaraqe/taskx#taskx -- list
```

## Basic commands

```bash
taskx add "Implement evaluator"   # create a task
taskx ready                       # tasks ready to be claimed
taskx list                        # all unfinished tasks
taskx show <uuid>                 # one task in detail
taskx start <uuid>                # claim a task
taskx note <uuid> "found bug X"   # append a note
taskx done <uuid>                 # complete a claimed task
taskx release <uuid>              # give it back up
```

Tasks are referenced by UUID; unambiguous UUID prefixes are accepted. Every
task command also accepts `--json` for machine-readable output.

Dependencies between tasks:

```bash
taskx depends <uuid> add <other-uuid>
taskx depends <uuid> remove <other-uuid>
```

## Agents

taskx ships a skill for coding agents:

```bash
taskx skill install codex     # or claude, opencode
```

Agents should run `taskx help agent` for the built-in workflow summary.
