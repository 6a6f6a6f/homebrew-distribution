cask "jambor-beta" do
  version "0.2.1"
  sha256 "10066f7f3d07ec07f8a1bc711796656991c50b037bd20d45569a34becde0c822"

  url "https://assets.jojo.dev.br/jambor/launcher/installers/beta/0.2.1/3faa07acc3df5a7186f51495e25937e650995a54/jambor-0.2.1-3faa07acc3df5a7186f51495e25937e650995a54-osx-arm64.dmg"
  name "Jambor Beta"
  desc "Game launcher"
  homepage "https://jojo.dev.br/"

  depends_on arch: :arm64
  depends_on macos: :sonoma
  conflicts_with cask: "jambor"
  auto_updates true

  app "Jambor.app"

  caveats <<~EOS
    Experimental macOS beta: Developer ID signing and notarization are pending.
    macOS may block the first launch. See https://support.apple.com/102445.
    Updates are authenticated by Jambor. Native installation acceptance is pending.
  EOS
end
