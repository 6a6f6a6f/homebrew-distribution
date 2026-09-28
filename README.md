# Jambor distribution

Homebrew casks and WinGet manifests for Jambor. Binary artifacts are hosted on
https://assets.jojo.dev.br; installers and game assets are not stored in Git.

## Availability

No installable cask or WinGet package has been published yet. Installation commands
will be documented after native acceptance. Initial targets are macOS Apple Silicon,
Windows x64 and Windows ARM64. macOS Intel is not supported.

Experimental macOS downloads will be labeled **Beta** while Developer ID signing and
notarization are pending. They must remain separate from signed stable releases and
the signed automatic-update feed.

## Package layout

Add validated packages when available:

- `Casks/jambor.rb`: Homebrew cask with an immutable URL, explicit version and SHA-256.
- `winget/manifests/`: versioned WinGet manifests in the community repository layout.

This repository serves as a Homebrew tap. WinGet manifests are submitted to
`microsoft/winget-pkgs`; this Git repository is not itself a WinGet source endpoint.
Package availability in that catalog depends on upstream acceptance.

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
