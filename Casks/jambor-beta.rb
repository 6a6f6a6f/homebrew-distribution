cask "jambor-beta" do
  version "0.3.0"
  sha256 "b33687708bc3e0b5fb890695535bf72e3589a2813faf9478f6207855290e2fa7"

  url "https://assets.jojo.dev.br/jambor/launcher/installers/beta/0.3.0/b9bda4d1cb06b3bd08744ee3a8ec943756730540/jambor-0.3.0-b9bda4d1cb06b3bd08744ee3a8ec943756730540-osx-arm64.dmg"
  name "Jambor Beta"
  desc "Game launcher"
  homepage "https://jojo.dev.br/"

  depends_on arch: :arm64
  depends_on macos: ">= 14.0"
  conflicts_with cask: "jambor"
  auto_updates true

  app "Jambor.app"

  caveats <<~EOS
    Experimental macOS beta: Developer ID signing and notarization are pending.
    macOS may block the first launch. See https://support.apple.com/102445.
    Updates are authenticated by Jambor. Native installation acceptance is pending.
  EOS
end
