cask "jambor-beta" do
  version "0.2.0"
  sha256 "acf40933f1c79a1be05677b1319847d7a04453f6ec1370069e4834e5eeea5055"

  url "https://assets.jojo.dev.br/jambor/launcher/installers/beta/0.2.0/a11a435af5a9134b63c63abfcb7ffc247a1bda5f/jambor-0.2.0-a11a435af5a9134b63c63abfcb7ffc247a1bda5f-osx-arm64.dmg"
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
