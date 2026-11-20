# Third-party visual assets

- EVO is retrieved on first selection directly from the [official Brahma-Ai-Evo repository](https://github.com/titechprabhasolutions/Brahma-Ai-Evo) into the local JINX data folder. The upstream license prohibits mirroring or uploading its source files to Git hosting, including private repositories, so the GitHub copy of JINX does not contain those files.
- `brahma_echo/`: assets from [Brahma-Echo](https://github.com/titechprabhasolutions/Brahma-Echo), licensed under the included Brahma Source-Available License. Preserve the license and source attribution; do not present these assets as JINX-authored.
- `qwen_neural/`: the "Orbe Neural Reativo à Voz" HTML page, authored with Qwen at the user's request (November 2026) and adapted to the HUD's native orb contract (setBrahmaState/setAudioLevel bridge, transparent embed mode, locally vendored three.js r128). Three.js r128 ships in this folder under its own MIT header; the page also references Google Fonts (OFL) presentationally, unused in embed mode.
- Three.js license notices are included in the upstream assets.
