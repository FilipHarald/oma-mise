# Security boundaries

This plugin runs as your user inside Omarchy's shared, unsandboxed Quickshell
process. The following guards limit malformed data and accidental resource use;
they do not turn a user-owned plugin or trusted mise templates into a sandbox.

## Runtime commands and data

- The shell launches `/usr/bin/python3 -I -S` with a cleared, allowlisted
  environment. Python helpers load their sibling `runtime.py` explicitly, not
  through the current directory or `PYTHONPATH`.
- Mise is selected only from `~/.local/bin/mise` or `/usr/bin/mise`, with held
  descriptor checks for owner, type and permissions. Its validated inode is used
  for execution. There is no arbitrary PATH or executable override fallback.
- Subcommands are fixed argument arrays. Status checks use the home directory;
  the only service mutation is an explicit start/stop of the existing
  `dev.mise.mise-history.service` through `/usr/bin/systemctl --user`.
- Python supplies a fixed `/usr/bin:/bin` PATH and C.UTF-8 locale, home-derived
  XDG config/data/state/cache directories, and no-color/noninteractive settings.
  User-systemd calls use `/run/user/<uid>/bus`. Ambient loader/interpreter,
  proxy, credential and mise command-override variables are not inherited.
  Nonstandard XDG config layouts and PATH-only mise installations are not
  supported by this helper. Copied commands run in the user's own terminal
  environment, only if the user chooses to paste and execute them.
- Mise status stdout is capped at 1 MiB and stderr at 64 KiB, while reading raw
  chunks, before JSON decoding. Overflow rejects the result rather than clipping
  it into a successful status. Counts are bounded and timestamps validated.
- Helpers return sanitized JSON, never raw CLI errors, paths or dotfile contents
  to the UI. QML separately caps status stdout at 64 KiB, watcher stdout at 4 KiB,
  and stderr at 4 KiB. Raw-chunk parsers check the budget before concatenation;
  no whole-output collectors or newline-dependent buffers are used.
- UI status models allow at most 32 detail strings, each at most 1,024 UTF-16
  units; summaries are at most 256 units. String/control-character, numeric,
  timestamp, property-name and watcher-control consistency checks fail closed.
  These schema limits supplement—not replace—the streaming byte limits.
- Every text element explicitly renders PlainText. The host bar tooltip has a
  separate markup/control-character guard and length limit. Icons are bundled
  local assets chosen from a closed set; no URL is derived from status data.

## Process lifetime

Python commands have absolute deadlines and capped stdout/stderr. A separate
Linux guardian watches a lifetime pipe, so termination of the helper—including
SIGKILL—still triggers descendant cleanup. It keeps the command leader unreaped
until the last group signal, then uses pidfds for adopted descendants that escape
the original session. TERM, KILL and bounded reap/drain phases also run on
normal completion and output overflow. This is not hostile fork-bomb containment;
user-space cleanup cannot force an uninterruptible kernel task to disappear.

QML adds outer deadlines of 20 seconds for status probes and 55 seconds for a
watcher action, followed by a one-second TERM-to-KILL grace. Watcher actions may
perform three sequential systemctl calls, each with its own 15-second deadline.
Polling remains single-flight and shared across monitors.

Copying does not launch a terminal, editor, mise command or shell. Only one of
three fixed home-scoped review command strings can reach wl-copy. Clipboard
ownership is intentionally different from a short status probe; see its lifetime
and removal behavior in the README.

## Files, installation and removal

Runtime status polling creates no plugin-owned status cache or credential file.
Mise may render trusted templates and may have its own effects. Starting its
watcher resumes the user's existing synchronization workflow, including possible
publication/application. Those behaviors are not disabled by the process guards.

The one-time ID migration is a separate, explicit terminal operation. See
[MIGRATION.md](MIGRATION.md) for descriptor-bound I/O, private backups, input
limits, locks, atomic publication, recovery, and the remaining limitations with
noncooperating same-user writers. It must run with the shell/config writers
stopped. It is never run automatically when the plugin loads.

See [Removing](../README.md#removing) for retained backups, development checkouts,
shared settings, clipboard state and the pre-existing mise service/data.

## Verification

The README commands run functional and security regressions, including real
subprocess overflow, timeout/descendant cleanup, isolated offscreen Quickshell
process tests, hostile models, and temporary-file migration races. Existing
functional tests remain in the suite.

Marketplace baseline scanning is a separate, narrower check. Service management
requires manual review even with no blocking pattern findings. A local review of
a private checkout is not marketplace approval, publication, or a guarantee
against all vulnerabilities. Git history review was waived by the owner.
