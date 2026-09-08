# Publishing oma-mise

The GitHub repository is **private** as verified on 8 September 2026. This document
is a checklist, not authorization to change visibility or publish social posts.

## Before making it public

- [x] Add a license for the plugin code: [MIT](../LICENSE), copyright 2026 FilipHarald.
- [x] Confirm the bundled logo's MIT copyright license: upstream
  `docs/public/logo-dark.svg` is covered by `docs/LICENSE` (copyright 2024 jdx).
  The full notice is included in [assets/LICENSE-mise](../assets/LICENSE-mise);
  [asset attribution](../assets/README.md) links the pinned source and license.
  Keep that notice when redistributing the recolored SVGs. This does not imply
  trademark permission or upstream endorsement.
- History review is waived by the repository owner; no history audit was performed.
- [x] Generalize installation paths; examples use `~/.local/share/oma-mise`.
- [x] Use the plugin ID `filipharald.oma-mise` while retaining the `oma-mise`
  repository name.
- [ ] Run the README verification commands and test on a clean Omarchy 4 machine
  with the documented mise history setup. A fresh authenticated clone of the
  private repo passed manifest validation during screenshot preparation; that is
  not a full fresh-desktop installation test.
- [ ] Add the Git installation command below and release notes to the public README.
- [ ] Only when explicitly approved: change GitHub visibility to public, then verify
  unauthenticated cloning works. No visibility change was performed here.
- [ ] Recommended: tag the reviewed commit `v0.1.0` (matching the manifest) and
  create a GitHub release with requirements, known limitations and screenshots.
  Neither a release nor a tag is required by the Git-based installer.

## Optional marketplace submission

Direct Git installation does not require a marketplace listing. For a curated
listing, the repository includes a root [`preview.png`](../preview.png): the
native green popup with staged demo data, with image metadata stripped.

- Use the marketplace's current submission form and a full reviewed commit SHA.
- Run the security baseline on that exact snapshot and resolve manual findings;
  a clean pattern scan is not a full security review. Watcher service management
  is an expected manual-review capability, not an automatic security pass.
- Keep the reviewed commit unchanged while approval is pending.
- The remote marketplace snapshot resolver requires a public repository. While
  private, run the analyzer on a local immutable Git snapshot instead and label
  that result as local analysis, not marketplace validation or approval.
- Review the [removal disclosure](../README.md#removing) along with runtime code.

No submission, release, tag, or visibility change is authorized by this checklist.

## Git distribution

The installed Omarchy CLI supports direct Git distribution. It clones a repo,
validates `manifest.json`, checks for duplicate plugin IDs, discovers it and can
enable it. There is no registry submission required for this installation path.
This does not imply acceptance into any curated community listing.

After the repository is public, new users can run:

```sh
omarchy plugin add https://github.com/FilipHarald/oma-mise.git --enable
```

While private, collaborators with GitHub access and configured SSH can instead use:

```sh
omarchy plugin add git@github.com:FilipHarald/oma-mise.git --enable
```

These are **new-install** commands. If the plugin is already installed as a
development symlink, keep that checkout and symlink instead of installing a duplicate.
For installations managed by the Git installer, updates are:

```sh
omarchy plugin update filipharald.oma-mise
```

Plugins run as unsandboxed code in the desktop shell. Users should review the code
before enabling. This plugin's status checks read local mise state; explicit
watcher controls start/stop the existing user service and can resume sync.

## Social images

See [`../screenshots/README.md`](../screenshots/README.md). Download the PNGs locally
and attach them to X posts; private GitHub/raw links are not public image hosting.
The images are staged demo states, not reports of real sync incidents.
No X post was created. No public repository, release or registry submission was made.

## Sources checked

- Installed `omarchy plugin --help` and
  `/usr/share/omarchy/bin/omarchy-plugin-add`: Git install/enable, schema validation,
  duplicate-ID checks and trust warning.
- Installed `/usr/share/omarchy/default/agents/skills/omarchy/plugins.md`: plugin
  locations, discovery and reload behavior.
- `gh repo view FilipHarald/oma-mise --json visibility,url`: private repository.
