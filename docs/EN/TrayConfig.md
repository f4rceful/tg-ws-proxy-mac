# macOS configuration

Application files are stored in `~/Library/Application Support/TgWsProxyMac`, independently of the original application. `config.json` stores proxy settings, `proxy.log` stores logs and `.update_check_cache.json` caches release metadata.

- `check_updates`: check this fork's public GitHub releases at launch. Updates are installed only after confirmation. The release must contain `TgWsProxyMac_universal2.dmg` with a GitHub SHA-256 digest.
- `autostart`: login startup preference. The effective state is read from `~/Library/LaunchAgents/com.github.f4rceful.tgwsproxymac.plist`. Use the macOS login section of settings in the packaged app to change it; editing JSON does not create a LaunchAgent.
- `language`: `auto` follows macOS (Russian when primary, English otherwise); `ru` and `en` explicitly select a language. Restart after editing this value manually.

Other fields and the full example are described in the [configuration reference](../TrayConfig.md). Settings are written atomically. Update recovery copies are stored beside the app in `.tgws-mac-update-*`; the newest valid copy is retained.

- `appearance`: `auto` follows macOS; `light` and `dark` select an appearance. Language and appearance can also be changed in the settings form.
