cask "jambor-beta" do
  version "0.4.1"
  sha256 "0ff4cac9adc4ad1a7e8ea1f2b1531fcbca7bf2676ca383efd618a2879341d2f0"

  url "https://assets.jojo.dev.br/jambor/launcher/installers/beta/0.4.1/c63cda48ec858d28a186dd9fa5aaa00d67f8d9ed/jambor-0.4.1-c63cda48ec858d28a186dd9fa5aaa00d67f8d9ed-osx-arm64.dmg"
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
