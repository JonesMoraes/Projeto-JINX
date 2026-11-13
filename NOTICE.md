# NOTICE — JINX

Expansion task 1.1 (2026-11-13): Gemini account configuration plugin adapted
from João Gabriel / jgm-source/jarvis-opensource, CC BY-NC 4.0,
commit 87d9ea2bfd600e189ba849a0653039e8c505c978,
plugins/gemini_accounts.py. Primary-first fallback design also informed
core/gemini_accounts.py; retry integration and tests adapted to JINX's ladder.
Source: https://github.com/jgm-source/jarvis-opensource/tree/87d9ea2bfd600e189ba849a0653039e8c505c978
Existing FatihMakes attribution and non-commercial restrictions remain.

Expansion task 1.2: Trello configuration, matching and agenda reconciliation
adapted from plugins/trello_control.py and core/agenda_sync.py in the same
jgm-source commit above (João Gabriel, CC BY-NC 4.0). The JINX adaptation
separates transport/store/UI, adds verified readback and undo, preserves
conflicts instead of deleting events and uses no upstream accounts or servers.

Expansion task 1.3: local organizer adapted from plugins/organizer.py in
jgm-source/jarvis-opensource, commit 87d9ea2bfd600e189ba849a0653039e8c505c978
(João Gabriel; original Mark attribution retained; CC BY-NC 4.0). The JINX
adaptation uses a compact task/event interface, existing shared agenda storage,
atomic writes, per-item undo and soft archive. No account data was imported.

Expansion task 1.4: Cakto sales integration adapted from plugins/cakto_sales.py
in jgm-source/jarvis-opensource at commit
87d9ea2bfd600e189ba849a0653039e8c505c978 (João Gabriel; CC BY-NC 4.0).
Adaptations: separate read-only client, exact decimal totals, payment-date
filters, currency isolation, bounded pagination with explicit partial results,
credential-specific in-memory token cache and minimized order summaries.
No source credentials, customer diagnostic files or private servers imported.

Expansion task 1.5: Rastracking SALES/client/support contract adapted from
plugins/rastracking.py in jgm-source/jarvis-opensource, commit
87d9ea2bfd600e189ba849a0653039e8c505c978 (João Gabriel; CC BY-NC 4.0).
Adaptations: user-provided HTTPS server with no default, read-only endpoints,
Decimal aggregates, bounded cursor pagination and explicit partial results,
support subjects only on explicit request, no diagnostic files or credentials.
Parcel tracking is a separate original implementation against the published
Correios API contract, not a feature ported from the Rastracking source.
Brahma assets present on this machine are excluded from Git and are not
relicensed by this notice. Their existing HUD integration is a recorded
remediation item; it is not represented as an independently authored visual.

JINX is a modified, **non-commercial** derivative of **Mark-LVII**
("MARK LVII") by FatihMakes:

  https://github.com/FatihMakes/Mark-LVII

Original license (retained — see `LICENSE`):

  Creative Commons Attribution-NonCommercial 4.0 International
  https://creativecommons.org/licenses/by-nc/4.0/

What was changed in this fork:

  - The product and every identifier were renamed: `JARVIS` → `JINX`,
    `Mark-LVII` / `MARK LVII` → `JINX`.
  - README and setup texts were updated to JINX and to credit the original.
  - No functionality was removed or relicensed.

Every design, feature and line of the original code belongs to FatihMakes
and the other authors of the original project. This derivative is used
under the terms of CC BY-NC 4.0 and **may not be used commercially**.

Wake word: the built-in "Hey Jarvis" wake phrase is provided by the
pretrained openwakeword model `hey_jarvis`, which is why that name is
retained in the code.
