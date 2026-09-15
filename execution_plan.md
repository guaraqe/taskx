# taskx v1 execution plan

## 1. Decisions and constraints

The implementation follows `initial_design.md` with these settled details:

- Taskwarrior storage uses the string UDAs `taskx_created_by`,
  `taskx_started_by`, and `taskx_closed_by`.
- Public JSON uses `created_by`, `started_by`, and `closed_by`; storage names
  are not part of the public interface.
- Project filters use exact matching (`project.is:<git-root-basename>`), and
  Taskwarrior contexts are disabled for every adapter invocation.
- `done` requires an active task that has `taskx_started_by`. A released task
  must be started again before completion.
- Every mutation, including `note`, runs under the taskx process lock. The lock
  covers validation, mutation, and postcondition verification.
- Python 3.11 remains the minimum supported Python version. Initial integration
  development targets Taskwarrior 3.x and is verified against Taskwarrior 3.5.
- Runtime Python dependencies are managed and locked by uv.

The development stack is:

- `uv` for environments, locking, dependency management, running tools, and
  the build backend;
- Ruff for formatting and linting;
- ty for static type checking;
- pytest for tests.

`flake.nix` provides the small development toolchain: Python 3.11, `uv`, Ruff,
ty, Taskwarrior, and Git. NixOS cannot directly execute the generic
Linux binaries distributed through uv for Python, Ruff, and ty without a
host-wide `nix-ld` configuration, so the flake supplies those executables while
uv owns Python runtime and development dependencies, the project environment,
dependency lock, build backend, and standard command-running interface. Version
1 does not define a Nix package output.

## 2. Part I — primary-agent scaffolding

The primary agent completes this part first and owns the shared contracts and
files that would otherwise cause conflicts between subagents.

### 2.1 Project and development environment

Create:

- `pyproject.toml` using the uv build backend and a `taskx` console script;
- focused Ruff, ty, and pytest configuration in `pyproject.toml`;
- `.python-version`, `uv.lock`, `.gitignore`, and a minimal `flake.nix`;
- the `src/taskx/` package and `tests/` directory skeleton.

The standard verification interface is:

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

### 2.2 Shared contracts

Define before delegation:

- the normalized `Task` model and stable JSON field names;
- command exit codes and the exception hierarchy;
- UUID and unique-prefix resolution behavior;
- the Taskwarrior adapter protocol and subprocess result/error boundary;
- actor detector ordering and the environment mapping interface;
- lock scope and path policy;
- CLI parser shape, including consistent placement of `--json`.

The normalized task representation includes at least UUID, description,
project, status, active, blocked, waiting, dependency UUIDs, annotations,
entry/start/end/wait/scheduled timestamps, and the three normalized actor
fields. Taskwarrior numeric IDs never cross the adapter boundary.

### 2.3 Test infrastructure

Build fixtures that:

- create temporary Git repositories;
- run Taskwarrior against isolated `TASKDATA` and configuration;
- never read or mutate the developer's Taskwarrior database;
- allow actor environment overrides;
- support subprocess-level concurrency tests;
- skip integration tests with a clear reason when `task` is unavailable.

### 2.4 Delegation gate

Before subagents start, the primary agent runs the empty/skeleton quality suite
successfully and commits or otherwise establishes a clean integration baseline.
Subagents receive bounded file ownership and acceptance tests. They do not edit
`pyproject.toml`, `flake.nix`, shared protocols, or unrelated modules unless a
contract defect is reported to the primary agent.

## 3. Part II — GLM subagent work packages

These packages are deliberately small. They are dispatched in waves so that a
later package builds only on reviewed interfaces.

Delegation uses Paseo agent-scoped subagents running GLM 5.3 Flash. At execution
time, the primary agent first inspects Paseo's configured profiles and provider
catalog, selects the matching GLM 5.3 Flash launch configuration, and preserves
the provider's configured mode and thinking settings. Agents work in the current
workspace with exclusive file ownership assigned in each prompt; dependency
waves and primary-agent review prevent concurrent edits to shared files.

### Wave A — independent foundations

#### A1. Git project resolver

Owner: GLM subagent.

Implement `project.py` and its tests: Git-root discovery, basename extraction,
clear failure outside a repository, whitespace-safe subprocess arguments, and
exact project-filter construction.

#### A2. Actor resolver

Owner: GLM subagent.

Implement `actor.py` and its tests: `TASKX_ACTOR` override, isolated Codex,
Claude Code, and OpenCode detectors, deterministic precedence, and
`human:<username>` fallback. Empty detector values must not win.

#### A3. Process lock

Owner: GLM subagent.

Implement `locking.py` and its tests using POSIX advisory locking. Verify that
process exit releases the lock and concurrent mutation critical sections do
not overlap.

### Wave B — Taskwarrior boundary

#### B1. Export normalization

Owner: GLM subagent.

Implement Taskwarrior JSON-to-model normalization and tests. Cover missing
optional fields, Taskwarrior 3 waiting representation, annotations,
dependencies, timestamps, orphan metadata, and removal of numeric IDs.

#### B2. Read adapter

Owner: GLM subagent.

Implement read-only adapter operations: exact-project export, lookup by full or
unique UUID prefix, ready filtering with active tasks excluded, pending-plus-
waiting listing, and calculated blocked state. Disable Taskwarrior contexts and
keep subprocess invocation shell-free.

#### B3. Mutation primitives

Owner: GLM subagent.

Implement low-level add, start, stop, done, annotate, and dependency mutation
operations using underscore UDAs and runtime UDA definitions. Use `--` for
literal descriptions/annotations, capture new UUID output in automation mode,
and return structured failures without printing success prematurely.

### Wave C — command behavior

#### C1. Inspection commands

Owner: GLM subagent.

Implement and test `actor`, `project`, `ready`, `list`, and `show` command
handlers against the shared CLI and presentation contracts.

#### C2. Creation and context commands

Owner: GLM subagent.

Implement and test `add`, `note`, and `depends`, including UUID resolution,
self-dependency rejection, cross-project rejection, and Taskwarrior's cycle
failure propagation.

#### C3. Lifecycle commands

Owner: GLM subagent.

Implement and test `start`, `release`, and `done`. The lock must enclose
precondition checks, the mutation, and re-export verification. Cover blocked,
waiting, scheduled, already-active, released, and never-started cases.

### Wave D — user-facing completion

#### D1. Agent help and README

Owner: GLM subagent.

Implement `taskx help agent` and draft the README with installation,
development, lifecycle, JSON, error, and minimal `AGENTS.md` examples. Do not
add Markdown task tracking or Nix package instructions.

#### D2. Integration and concurrency tests

Owner: GLM subagent.

Add black-box tests for the complete lifecycle, exact project isolation,
Taskwarrior contexts, literal modifier-like descriptions, cross-project
dependencies, postcondition failures, and two processes attempting to start
the same task.

## 4. Primary-agent integration and release gate

After every wave, the primary agent reviews behavior against the design,
resolves interface issues centrally, and runs all four quality commands. The
primary agent retains ownership of cross-cutting CLI integration, error
consistency, and any changes to shared contracts.

Version 1 is ready only when:

1. the full quality suite passes from a fresh `nix develop` shell;
2. the lifecycle integration test proves that exactly one concurrent actor can
   claim a task;
3. completed tasks disappear from normal `ready` and `list` output;
4. all task operations enforce exact Git-project isolation;
5. raw Taskwarrior state contains the correct underscore attribution UDAs;
6. the repository can be installed and invoked through uv/pip-compatible Python
   tooling without any runtime Python dependency;
7. no Nix package derivation or secondary task database has been introduced.

## 5. Execution record

Execution completed on 2026-09-10.

Part I established the uv build and environment metadata, the minimal Nix
development shell, normalized task/error/subprocess/CLI contracts, isolated
Git and Taskwarrior fixtures, and the standard quality gate.

Part II was executed through Paseo with the configured GLM 5.3 Flash profile.
The delegated packages delivered Git project resolution, actor detection,
POSIX mutation locking, Taskwarrior normalization/read/mutation layers, all
command-handler groups, agent help and README documentation, and black-box
integration/concurrency coverage. The primary agent reviewed each result and
owned concrete adapter composition, CLI runtime dispatch, shared-contract
changes, and release verification.

The final gate passes from `nix develop` with 171 pytest tests, including a
real two-process claim race in which exactly one start succeeds. Ruff format,
Ruff lint, and ty all pass. A Python source distribution and wheel build
successfully through uv. No Nix package derivation or secondary task database
was added.
