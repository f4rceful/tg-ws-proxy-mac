# TG WS Proxy Mac

A macOS-only fork of [Flowseal/tg-ws-proxy](https://github.com/Flowseal/tg-ws-proxy). Download a build from [this fork's releases](https://github.com/f4rceful/tg-ws-proxy-mac/releases) when one is published, or follow the [build guide](../Development.macos.md).

1. Open the universal DMG and drag **TG WS Proxy Mac.app** into **Applications**.
2. Launch it and choose **Open in Telegram (127.0.0.1:1443)** from the menu bar.
3. Confirm the proxy in Telegram Desktop.

The application runs in the menu bar. **Copy link**, **Restart proxy**, **Settings...** and **Open logs** retain their original workflows. Settings use compact, sequential native dialogs; **Close** discards unsaved changes. At the end, the application asks whether to restart the proxy.

Windows and buttons use Liquid Glass on macOS 26 and later, with standard translucent AppKit controls on macOS 11–15. The menu bar icon adapts to light and dark appearances. The UI supports Russian and English and follows the macOS language by default.

## Login startup

The final settings dialog in a packaged application enables startup at macOS login using a per-user LaunchAgent. Install the application in a permanent folder first. After moving it, enable startup again. This option is hidden when running from source.

## Updates and recovery

**Update** appears in the menu and settings dialogs when a newer public release is available. **Check for updates...** requests a manual check. Installation requires confirmation, downloads `TgWsProxyMac_universal2.dmg` from this fork, verifies its GitHub SHA-256 digest, bundle identity and version, executable and code signature, and prepares a replacement before quitting.

The previous application is retained. If replacement or the launch command fails, the installer restores it. On subsequent starts, older valid backups are cleaned up and the newest backup remains at `.tgws-mac-update-*/previous.app` beside the application. Exit is blocked during update preparation.

Updating from a mounted DMG, App Translocation or a folder without write access is unavailable. Running from source opens the release page instead. Draft releases and Actions artifacts are excluded; a public release must be published separately before updates can be offered.

See [configuration](./TrayConfig.md) or the [Russian guide](../README.md).
