# Jambor distribution

Homebrew casks, WinGet proposal sources, and the Ubuntu APT archive generator for
Jambor. Binary artifacts are hosted on https://assets.jojo.dev.br; installers and
game assets are not stored in Git.

There is one distribution channel. Pre-1.0 builds may ship ad-hoc (macOS) or
unsigned (Windows) installers; feeds remain RSA-authenticated. Do not reintroduce
retired `jambor-beta` / `Jojo.Jambor.Beta` package IDs or `/beta/` asset paths.

## Ubuntu APT archive

`apt/repository.py` generates the Ubuntu 26.04 archive (`Suite: ubuntu-26.04`) for
AMD64 and ARM64 from reviewed launcher `.deb` files. It uses Python, `dpkg-deb`,
`apt-ftparchive` and GnuPG; it does not rebuild application installers. Binary
packages/indexes belong on R2, not in this repository. `apt/keys/` contains public
keys only.

Run `python3 -m unittest discover -s apt -v` on Ubuntu with `apt-utils` and `gnupg`.
Tests use disposable keys and isolated APT lists; they do not install fixtures.
Jambor pins this generator's exact commit and performs protected publication.
See [APT operations](https://github.com/6a6f6a6f/jambor/blob/main/docs/apt-repository.md)
for enrollment, ownership, rotation, renewal and acceptance.

## Package layout

- `Casks/jambor.rb`: Homebrew cask with an immutable URL, explicit version and SHA-256.
- `downloads/stable.json`: site-facing installer matrix mirror used by catalog tooling.

This repository is a Homebrew tap. WinGet manifests are proposed to
`microsoft/winget-pkgs` through the `6a6f6a6f/winget-pkgs` fork; this Git repository
is not a WinGet source endpoint. Package availability in that catalog depends on
upstream acceptance.

## Publication

Generate package metadata from accepted launcher release manifests, preserving exact
artifact URLs and hashes. Never use mutable installer URLs or `sha256 :no_check`.
Retries reuse accepted bytes; corrections receive a higher version. Credentials and
private keys must never appear in this repository or untrusted pull-request jobs.

## Self-update integration

The launcher owns mandatory application updates. Integration with installation records
still needs implementation and native validation:

- Homebrew casks declare `auto_updates true`. App updates carry the correct bundle
  version; the launcher does not modify Homebrew receipts or Caskroom metadata.
- Windows updates reconcile installed-version and uninstall registration only after
  successful installation. Use the chosen installer's supported mechanisms; never
  manually modify MSI-managed state or silently elevate.
- Test package-manager upgrades after self-updates and the reverse order, including
  reinstalls, recovery and removal. Preserve user data and prevent downgrades when
  catalog publication lags behind an installed release.

## References

- https://docs.brew.sh/Cask-Cookbook
- https://docs.brew.sh/Taps
- https://learn.microsoft.com/en-us/windows/package-manager/package/manifest
- https://learn.microsoft.com/en-us/windows/package-manager/package/repository
