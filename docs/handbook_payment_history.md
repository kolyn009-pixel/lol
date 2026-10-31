# Handbook navigation, payment evidence and mobile student layout

The handbook starts with subject tiles, then sections and topics. Search opens matching formulas directly. Grade ranges, student favourites, KaTeX rendering, formula details and existing teaching actions remain in use. No formula metadata is reassigned. The API currently caps the loaded catalogue at 500 records.

Teacher finances add a read-only explanation of a lesson/payment state, including existing receipt reviews, minute ledger records, package links and group confirmation audit records. Missing historical actors and sources are explicitly unknown. The correction journal reads payment reversals and individual/group balance returns. These are accounting corrections, not proof of a bank refund. It does not execute refunds, approvals or backfills. Existing unexplained production PAID statuses still require the read-only production diagnostic; this change does not establish their cause or reverse them.

The students stylesheet had an unfinished grid declaration. A reviewed surgical hook closes it; mobile overrides remove intrinsic wide filter/list columns, use a two-column filter grid and one-column student cards. Known overlay containers are constrained to the viewport, hidden overlays remain hidden, and filter dialogs attach to body outside page stacking contexts. The exact cause of the user's blurred iPhone screen has not been reproduced; native device validation remains necessary.

`install_release_ui.py` includes the new files and reviewed hooks while preserving production HTML and unrelated server edits. It accepts only a recorded installed asset hash or the explicitly reviewed previous handbook version. Unknown local changes stop the installer before mutation. No deployment or application builds were performed for this change.

Validation: read-only SQLite fixtures for unknown legacy sources, package links, group binding and correction journal; DOM tests for catalogue navigation/search/grade ranges and history dialogs; CSS cascade checks at 375/390/430/768/900 widths. These checks are not iPhone screenshots or native application acceptance tests.
