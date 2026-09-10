# Skill installer

## Goal

Add a taskx command that installs the bundled task-management skill for one
supported coding agent. Installation is repository-local by default and may be
made user-global explicitly.

## Command surface

```text
taskx skill install codex [--global]
taskx skill install claude [--global]
taskx skill install opencode [--global]
```

The agent name is a required subcommand beneath `install`. No implicit agent
detection is performed.

## Destinations

| Agent | Local | Global |
| --- | --- | --- |
| Codex | `<git-root>/.agents/skills/taskx/SKILL.md` | `~/.agents/skills/taskx/SKILL.md` |
| Claude | `<git-root>/.claude/skills/taskx/SKILL.md` | `~/.claude/skills/taskx/SKILL.md` |
| OpenCode | `<git-root>/.opencode/skills/taskx/SKILL.md` | `~/.config/opencode/skills/taskx/SKILL.md` |

Local installation resolves the Git root from the current directory. Global
installation does not require a Git repository.

## Packaging and writes

The wheel carries the skill as package data and the installer copies its exact
bytes to the target. The root `SKILL.md` remains the repository-facing copy and
a test keeps it identical to the bundled copy.

Create missing parent directories. If the target is absent, install it. If it
already has identical content, report success without rewriting it. If it has
different content, fail with a conflict rather than overwriting user changes.
Do not delete unrelated files in an existing skill directory.

Successful text output names the installed or already-current target path.
Expected filesystem errors use taskx's normal concise error presentation.

## Dependency decision

Keep the implementation in the Python standard library. The evaluated Python
installers either omit OpenCode, use obsolete destination paths, or pull in a
larger registry/TUI/MCP dependency tree for a small deterministic copy operation.

## Verification

- Parser tests cover all three nested agent subcommands and `--global`.
- Unit tests cover every local/global destination, Git-root resolution from a
  nested directory, global use outside Git, idempotence, conflict preservation,
  and exact bundled content.
- A built-wheel test confirms the packaged skill is present.
- Existing Ruff, ty, pytest, flake, and build gates remain green.
