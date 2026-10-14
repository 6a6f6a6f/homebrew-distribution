cask "jambor" do
  version "0.4.2"
  sha256 "9a7fe4fa63c70447d441b821fab5cf5928a589fced7ac98ef7e112c3c6eb55b8"

  url "https://assets.jojo.dev.br/jambor/launcher/installers/0.4.2/9df77ca63f2d096a4503094120ffbda642818bd8/jambor-0.4.2-9df77ca63f2d096a4503094120ffbda642818bd8-osx-arm64.dmg"
  name "Jambor"
  desc "Game launcher"
  homepage "https://jojo.dev.br/"

  depends_on arch: :arm64
  depends_on macos: :sonoma
  auto_updates true

  app "Jambor.app"

  caveats <<~EOS
    Pre-1.0 Jambor: Developer ID signing and notarization may be pending.
    macOS may block the first launch. See https://support.apple.com/102445.
    Updates are authenticated by Jambor.
  EOS
end
