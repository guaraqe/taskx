
# taskx

## 1. Purpose

`taskx` is a small Python CLI for managing project-specific development tasks through Taskwarrior.

It is primarily intended for software projects developed with AI coding agents, although it should remain convenient for direct human use.

The problem it addresses is that task lists stored in Markdown tend to become stale:

* agents complete work without updating the task list;
* completed tasks remain permanently visible;
* old tasks consume model context and distract agents;
* multiple agents can interpret or edit task state inconsistently;
* task state is mixed with design and documentation prose.

`taskx` makes Taskwarrior the canonical source of mutable task state. Agents should normally see only tasks that are currently relevant.

The tool is deliberately small. It is a project-aware interface to Taskwarrior, not a replacement for Taskwarrior and not an AI orchestration framework.

---

## 2. Design principles

### Task state belongs in Taskwarrior

`taskx` must not maintain its own task database, JSON file, Markdown file, or event log.

All canonical task state must be representable as Taskwarrior tasks and attributes.

### Project scope is implicit

The current Git repository determines the Taskwarrior project automatically.

Running:

```bash
taskx ready
```

inside:

```text
/home/user/src/wirecat/
```

operates only on:

```text
project:wirecat
```

The user or agent should not normally need to specify a project.

### Completed work is invisible by default

Normal commands must never include completed or deleted tasks unless the user explicitly asks for them.

The primary agent workflow therefore remains bounded by the current working set rather than the entire history of the project.

### UUIDs are the canonical identifiers

Taskwarrior numeric IDs are mutable presentation identifiers and must not be used by the `taskx` interface.

All task references exposed by `taskx` use Taskwarrior UUIDs.

Abbreviated UUID prefixes may optionally be accepted when they resolve uniquely, but output should contain the full UUID in JSON.

### Lifecycle transitions are explicit

Working on a task follows:

```text
pending
   │
   ├── taskx start
   ▼
active
   │
   ├── taskx done ───────► completed
   │
   └── taskx release ────► pending
```

An AI agent that starts a task should either complete it or release it before abandoning the work.

### Agent identity is recorded automatically

The agent should not need to remember or manually provide its identity.

`taskx` determines the current actor from its environment and records it when relevant lifecycle operations occur.

---

## 3. Non-goals

Version 1 does not:

* manage design documents;
* impose a documentation directory structure;
* parse Markdown task lists;
* infer whether implementation work is complete;
* automatically reconcile stale tasks with source code;
* invoke an LLM;
* manage Git branches or worktrees;
* synchronize tasks with GitHub, Linear, Jira, etc.;
* implement its own persistence;
* preserve a complete append-only history of every task lifecycle event;
* replace general Taskwarrior functionality.

Design documents remain ordinary files in the repository. A task may mention a design document path in its description or annotation, but `taskx` assigns no semantics to that reference.

---

## 4. Requirements

`taskx` requires:

```text
Python >= 3.11
git
Taskwarrior
```

Runtime Python dependencies should preferably be zero.

Use the standard library unless a dependency provides a substantial benefit.

The initial supported environment is POSIX-like development systems. Linux is the primary target.

---

## 5. Project detection

The project is determined from the Git repository containing the current working directory.

Equivalent operation:

```bash
git rev-parse --show-toplevel
```

Given:

```text
/home/juan/src/wirecat
```

the Taskwarrior project is:

```text
wirecat
```

This is intentionally based only on the Git root basename.

No remote URL, GitHub organization, branch, or absolute path contributes to project identity.

If the current directory is not inside a Git repository, `taskx` must fail with a clear error.

Example:

```text
error: taskx must be run inside a Git repository
```

Two local repositories with the same root basename will therefore share a Taskwarrior project. This is an accepted v1 tradeoff.

---

## 6. Taskwarrior integration

All interaction with Taskwarrior must occur through the `task` executable.

`taskx` must never:

* access Taskwarrior's SQLite/TaskChampion files directly;
* depend on Taskwarrior's internal storage layout;
* mutate Taskwarrior storage outside its public CLI.

For reads, prefer:

```bash
task ... export
```

and parse the resulting JSON.

Every invocation must disable the user's active Taskwarrior context with a
runtime `rc.context=` override. Project selection must use Taskwarrior's exact
`project.is:<name>` filter so hierarchical subprojects do not leak into the
current repository's task set.

For writes, use normal Taskwarrior commands or its supported JSON import interface where doing so materially improves correctness.

The implementation should centralize all Taskwarrior subprocess interaction behind a small adapter rather than scattering subprocess calls through command handlers.

Conceptually:

```text
CLI
 │
 ├── GitProjectResolver
 ├── ActorResolver
 │
 └── TaskwarriorAdapter
         │
         └── task executable
```

---

## 7. taskx metadata

`taskx` adds the following Taskwarrior UDAs:

```text
taskx_created_by
taskx_started_by
taskx_closed_by
```

All three are strings.

Version 1 uses a `taskx_` prefix rather than dotted names. Taskwarrior 3.5 does
not accept dotted UDA names as ordinary CLI modifiers, while underscore names
allow attribution and lifecycle changes to occur in the same Taskwarrior
command.

### `taskx_created_by`

Actor that created the task through `taskx`.

Set automatically by:

```bash
taskx add
```

It never changes.

Tasks originally created directly through Taskwarrior may not contain this field.

### `taskx_started_by`

Actor that most recently successfully started the task.

Set automatically by:

```bash
taskx start
```

A task that is active must have `taskx_started_by`.

This field remains after a task is released. A later `start` overwrites it.

Therefore:

```text
ACTIVE + taskx_started_by
```

means "currently being worked on by this actor."

On a non-active task, the field means "most recent actor that started this task."

Version 1 intentionally does not preserve earlier starters.

### `taskx_closed_by`

Actor that completed the task through:

```bash
taskx done
```

It must be populated before a task becomes completed through `taskx`.

---

## 8. Actor identity

Actor identity is represented as a string.

Examples:

```text
codex:019c...
claude:abc123...
opencode:ses_...
human:juan
```

Actor resolution uses the following precedence:

```text
TASKX_ACTOR
known AI harness session environment variables
human:<local username>
```

`TASKX_ACTOR` is an explicit override and must always take precedence.

For known AI environments, implement small independent detectors. Initial detectors should include known session identifiers exposed by Codex and Claude Code, and support an OpenCode session identifier when one has been injected into the process environment.

Actor detection must be isolated behind an interface such as:

```python
def current_actor(env: Mapping[str, str]) -> str:
    ...
```

so additional harnesses can be added without affecting task logic.

`taskx actor` should print the resolved actor for debugging.

Example:

```bash
$ taskx actor
codex:019ca7...
```

The fallback `human:<username>` ensures that `started_by` can always be populated.

---

## 9. Commands

### `taskx ready`

Show tasks that can currently be taken by a new worker.

```bash
taskx ready
taskx ready --json
```

A ready task must:

```text
belong to the current project
be pending
not be blocked by an incomplete dependency
not be waiting
not be scheduled for the future
not currently be active
```

The final condition is important.

Taskwarrior itself may consider an already-started task actionable, but `taskx ready` treats an active task as claimed and must not offer it to another agent.

Normal output should be concise.

JSON output is intended for programmatic/agent use.

---

### `taskx list`

Show all currently pending tasks for the project, including waiting tasks.

```bash
taskx list
taskx list --json
```

Unlike `ready`, this may include:

```text
active
blocked
waiting
future-scheduled
```

tasks.

It still must not show completed/deleted tasks.

This command is primarily for project inspection rather than choosing work.

---

### `taskx show`

Show one task.

```bash
taskx show <uuid>
taskx show <uuid> --json
```

The task must belong to the current project.

Output should include at least:

```text
UUID
description
status
active state
dependencies
annotations
created timestamp
start timestamp, if any
end timestamp, if any
taskx_created_by
taskx_started_by
taskx_closed_by
```

Missing optional metadata is allowed.

---

### `taskx add`

Create a task.

```bash
taskx add "Implement parser"
```

Optional dependencies:

```bash
taskx add "Implement evaluator" \
  --depends <uuid> \
  --depends <uuid>
```

Every dependency must resolve to a task in the current project.

The created task automatically receives:

```text
project:<current-project>
taskx_created_by:<current-actor>
```

The command prints the new UUID.

Example:

```text
created 80b65cb1-..."
```

JSON output should return the created task representation.

---

### `taskx start`

Claim/start a task.

```bash
taskx start <uuid>
```

Before starting, `taskx` must verify:

```text
task exists
task belongs to current project
task is pending
task is not blocked
task is not waiting/future-scheduled
task is not already active
```

If successful:

```text
taskx_started_by = current actor
Taskwarrior task becomes active
```

`started_by` is obligatory.

An already-active task must not silently change owner.

Example failure:

```text
error: task is already active
started_by: codex:019ca7...
```

This operation represents an agent claim.

---

### `taskx release`

Stop work without completing the task.

```bash
taskx release <uuid>
taskx release <uuid> --reason "Waiting for API decision"
```

The task must currently be active.

The command stops the Taskwarrior task and returns it to the normal pending pool.

`taskx_started_by` is intentionally retained as historical metadata.

If `--reason` is provided, it is stored as an ordinary Taskwarrior annotation.

A later `taskx start` may overwrite `started_by`.

---

### `taskx done`

Complete a task.

```bash
taskx done <uuid>
```

The command must refuse to complete a task unless it is currently active and
has been started through `taskx`. A released task must be started again before
completion unless an explicit future override mechanism is introduced.

Normal v1 invariant:

```text
start → done
```

Before completion:

```text
taskx_closed_by = current actor
```

must be stored.

Then Taskwarrior marks the task completed.

`closed_by` does not need to equal `started_by`.

This is intentional: one agent may finish or verify work started by another.

Completed tasks immediately disappear from `ready` and `list`.

---

### `taskx note`

Add unstructured context to a task.

```bash
taskx note <uuid> "Design: docs/parser.md"
taskx note <uuid> "The parser currently fails on nested tuples."
```

This maps to ordinary Taskwarrior annotations.

Annotations are context, not structured state.

No code should depend on parsing annotation contents.

This is also the mechanism for manually linking design documents in v1.

---

### `taskx depends`

Add or remove task dependencies.

Examples:

```bash
taskx depends <uuid> add <dependency-uuid>
taskx depends <uuid> remove <dependency-uuid>
```

Both tasks must belong to the current project.

Self-dependencies must be rejected.

Taskwarrior remains responsible for storing dependency relationships.

If feasible without significant complexity, obvious dependency cycles should be rejected before modification.

---

### `taskx actor`

Print the current automatically detected actor.

```bash
taskx actor
```

Useful when testing integration with an AI harness.

---

### `taskx project`

Print the automatically detected Taskwarrior project.

```bash
taskx project
```

Example:

```text
wirecat
```

---

### `taskx help agent`

Print a compact machine-oriented description of the workflow.

It should explain approximately:

```text
Project tasks are managed by taskx.

1. Run `taskx ready --json` to find available work.
2. Inspect a task with `taskx show <uuid> --json`.
3. Run `taskx start <uuid>` before modifying code for it.
4. When the task is complete and verified, immediately run
   `taskx done <uuid>`.
5. If abandoning or postponing active work, run
   `taskx release <uuid> --reason "..."`.
6. Use `taskx add` for newly discovered work.
7. Do not inspect completed tasks unless explicitly required.
8. Do not maintain parallel task lists in Markdown.
```

The purpose is to make `taskx` self-describing enough that an `AGENTS.md` only needs to say:

```text
Use `taskx` for project task management.
Run `taskx help agent` for its workflow.
```

---

## 10. JSON output

Agent-facing commands should support:

```bash
--json
```

JSON must be stable, simple, and independent of Taskwarrior's presentation-oriented numeric IDs.

Example:

```json
{
  "uuid": "80b65cb1-5fd2-4efa-b4a8-ebe17346b69c",
  "description": "Implement evaluator",
  "project": "wirecat",
  "status": "pending",
  "active": true,
  "blocked": false,
  "depends": [
    "352fc723-4178-4775-a05a-cb7c6f28ac51"
  ],
  "created_by": "human:juan",
  "started_by": "codex:019ca7...",
  "closed_by": null,
  "annotations": []
}
```

Taskwarrior-specific representation details should be normalized before being exposed through this interface.

No Taskwarrior numeric `id` should appear in the canonical JSON model.

---

## 11. Safety invariants

The implementation should enforce the following centrally rather than relying on AI instructions:

| Invariant                                | Requirement                                                    |
| ---------------------------------------- | -------------------------------------------------------------- |
| Project isolation                        | Every task operation is scoped to the current Git-root project |
| Stable identity                          | Task arguments resolve through UUIDs                           |
| No historical pollution                  | Normal listings exclude completed/deleted tasks                |
| No duplicate claims                      | `start` refuses an already-active task                         |
| Attribution                              | Every successful `start` sets `started_by`                     |
| Completion attribution                   | Every successful `done` sets `closed_by`                       |
| Dependencies                             | Blocked tasks cannot be started                                |
| No accidental cross-project dependencies | Dependencies must belong to the current project                |

Where an operation consists of multiple Taskwarrior mutations, the implementation should make failure behavior conservative.

A failed `start` must not leave the task appearing successfully claimed.

A failed `done` must not silently report completion.

If necessary, re-export the task after a mutation to verify the resulting invariant before reporting success.

---

## 12. Concurrency

Multiple local AI agents may invoke `taskx` concurrently.

The important race is:

```text
agent A checks task is free
agent B checks task is free
agent A starts task
agent B starts task
```

Version 1 should serialize mutating `taskx` operations with a lightweight process lock.

The lock only protects operations performed through `taskx`; it cannot protect direct concurrent calls to Taskwarrior.

The lock should cover at least:

```text
add
start
release
done
depends
note
```

Locking must remain an implementation detail. It should not introduce another persistent task database.

Read commands do not require the lock unless needed for consistent behavior.

---

## 13. Taskwarrior configuration

Users should not have to manually configure `taskx` UDAs merely to install the tool.

`taskx` should either:

1. supply the required UDA definitions as runtime Taskwarrior configuration overrides; or
2. provide a safe idempotent initialization mechanism.

Prefer runtime configuration if it works reliably with the supported Taskwarrior versions, because it avoids modifying the user's global `.taskrc`.

The required UDA schema is logically:

```text
taskx_created_by : string
taskx_started_by : string
taskx_closed_by  : string
```

---

## 14. Python structure

Suggested source layout:

```text
taskx/
├── pyproject.toml
├── README.md
├── src/
│   └── taskx/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── actor.py
│       ├── project.py
│       ├── model.py
│       ├── taskwarrior.py
│       └── locking.py
└── tests/
    ├── test_actor.py
    ├── test_project.py
    ├── test_commands.py
    └── test_taskwarrior.py
```

Responsibilities:

```text
cli.py
    argument parsing and presentation

actor.py
    AI session / human actor detection

project.py
    Git root and project-name resolution

model.py
    normalized task representation

taskwarrior.py
    all interaction with `task`

locking.py
    mutation serialization
```

Do not create abstractions beyond what is justified by these responsibilities.

---

## 15. Packaging

Expose:

```toml
[project.scripts]
taskx = "taskx.cli:main"
```

The project should be installable directly from Git:

```bash
pipx install git+https://github.com/<owner>/taskx
```

and eventually from PyPI without requiring packaging changes.

The runtime dependency list should ideally remain empty.

---

## 16. Testing

Tests should not operate on the developer's real Taskwarrior database.

Integration tests must run Taskwarrior against an isolated temporary data/config environment.

Tests should cover at minimum:

```text
Git project detection
failure outside Git repositories
actor precedence
human actor fallback
project scoping
task creation
UUID output
ready filtering
dependency blocking
start attribution
double-start rejection
release
completion attribution
completed-task disappearance
cross-project operation rejection
cross-project dependency rejection
JSON output
concurrent start attempts
```

The most important integration test is:

```text
create task
→ appears in ready

start task as actor A
→ does not appear in ready
→ started_by == actor A

attempt start as actor B
→ rejected

done task as actor A
→ status completed
→ closed_by == actor A
→ no longer appears in list or ready
```

---

## 17. Expected agent integration

A repository using `taskx` should need only minimal persistent instructions.

Example `AGENTS.md`:

```md
## Tasks

Use `taskx` for project task management.

Run `taskx help agent` before managing tasks.

Do not create or maintain Markdown task lists.
```

Detailed workflow knowledge belongs in the executable's help rather than being copied into every repository.

This is an intentional design goal: behavioral rules that can be enforced in code should be implemented in `taskx`; `AGENTS.md` should contain only enough information for an agent to discover the interface.

---

## 18. UDA versus event-log decision

Version 1 uses UDAs rather than a separate event log.

Taskwarrior already stores the important lifecycle state and timestamps. `taskx` only needs to attach actor identity to lifecycle transitions.

For the intended use case:

```text
created_by
started_by
closed_by
```

are directly queryable, machine-readable, and remain inside the single canonical persistence system.

The limitation is that:

```text
start A
release
start B
```

leaves:

```text
started_by = B
```

and does not preserve A as structured history.

This is accepted.

If complete lifecycle provenance later becomes important, it should be added deliberately as a new feature. It should not be emulated by parsing free-text Taskwarrior annotations.

---

## 19. Definition of done for v1

Version 1 is complete when a fresh repository can contain only:

```text
AGENTS.md → "Use taskx"
```

and an AI coding agent can independently:

```text
discover taskx usage
find actionable project tasks
claim exactly one task
inspect its metadata/dependencies
perform the work
record discovered tasks
complete or release its task
leave completed tasks outside future agents' normal context
record which AI/human session created, started, and completed tasks
```

without reading or modifying a persistent Markdown task list.
