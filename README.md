<div align="center">

# oma-mise

**Mise dotfiles, at a glance.**

A native Omarchy bar widget for sync activity, tracked-file counts, watcher
controls, and safe review commands.

</div>

![oma-mise showing healthy dotfiles](preview.png)

## Install

Once the repository is public:

```sh
omarchy plugin add https://github.com/FilipHarald/oma-mise.git --enable
omarchy bar move filipharald.oma-mise --section right --after omarchy.tray
```

For a private checkout or local development:

```sh
git clone git@github.com:FilipHarald/oma-mise.git "$HOME/.local/share/oma-mise"
mkdir -p "$HOME/.config/omarchy/plugins"
ln -s "$HOME/.local/share/oma-mise" \
  "$HOME/.config/omarchy/plugins/filipharald.oma-mise"
omarchy plugin enable filipharald.oma-mise
omarchy bar move filipharald.oma-mise --section right --after omarchy.tray
```

If discovery has not completed yet, run `omarchy-shell shell rescanPlugins` and
check `omarchy plugin list` before enabling. Use `omarchy restart shell` if QML
remains cached.

## What it does

- Shows local mise dotfiles health in the Omarchy bar.
- Displays file/checkpoint counts and recent publish, fetch, and apply activity.
- Refreshes every 30 seconds, on panel open, or from the refresh controls.
- Starts or stops only the existing `dev.mise.mise-history.service` user unit.
- Copies a fixed, home-scoped review command when attention is needed. It never
  launches a terminal/editor or executes the copied command.

Status checks run `mise bootstrap dotfiles status --json` from your home directory.
No dotfile contents, credentials, raw command errors, or status snapshots are
stored or shown. Trusted mise templates may execute while mise checks status.

Starting the watcher resumes your existing mise workflow and can publish or apply
pending changes. It does not change service enablement or mise configuration.

## Screenshots

These are native popup captures with staged demo data—not real sync incidents.

| Synced | Pending changes |
| --- | --- |
| ![Synced dotfiles](screenshots/green-synced.png) | ![Pending dotfile changes](screenshots/yellow-pending.png) |

| Sync conflict | Watcher paused |
| --- | --- |
| ![Dotfile sync conflict](screenshots/red-conflict.png) | ![Watcher paused](screenshots/paused-watcher.png) |

More capture details are in [`screenshots/README.md`](screenshots/README.md).

## Requirements

- [mise 2026.9.3 or newer](https://mise.jdx.dev/), with
  [dotfiles history configured](https://jdx.dev/posts/2026-09-07-dotfiles-that-save-themselves/)

## Removing

```sh
omarchy plugin remove filipharald.oma-mise
```

For a development symlink, Omarchy removes only the installed link and keeps the
source checkout. For a Git-managed installation it removes that installed clone;
save local edits first. Removing the monitor does not stop or delete the existing
mise watcher, configuration, dotfiles, history, or remotes. It installs no
credentials, sudoers/polkit rules, packages, hooks, or additional services.

## Development

```sh
python3 -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen QT_FORCE_STDERR_LOGGING=1 \
  /usr/lib/qt6/bin/qmltestrunner -input tests -o -,txt
omarchy plugin validate .
/usr/bin/python3 -I -S status.py
/usr/bin/python3 -I -S watcher.py status
```

Use Qt 6's test runner on Arch. For a live check:
`omarchy-shell filipharald.oma-mise open`.

## License

Plugin code is [MIT licensed](LICENSE). The bundled mise logo retains its upstream
ownership and MIT notice; see [`assets/README.md`](assets/README.md).
