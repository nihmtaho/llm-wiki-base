"""Old command paths, kept working as hidden aliases (spec §7).

Keys/values are path tuples. Registration lives in cli.py; this module is
the single source of truth so tests can assert completeness.
"""

OLD_TO_NEW: dict[tuple[str, ...], tuple[str, ...]] = {
    ("init", "personal"): ("setup", "personal"),
    ("init", "project"): ("setup", "project"),
    ("base", "install"): ("setup", "tools"),
    ("doctor",): ("setup", "doctor"),
    ("ingest",): ("wiki", "ingest"),
    ("reindex",): ("wiki", "reindex"),
    ("lint",): ("check", "lint"),
    ("verify",): ("check", "verify"),
    ("eval",): ("check", "eval"),
    ("proposals", "list"): ("review", "list"),
    ("proposals", "show"): ("review", "show"),
    ("proposals", "apply"): ("review", "apply"),
    ("proposals", "new"): ("review", "new"),
    ("proposals", "discard"): ("review", "discard"),
    ("base", "path"): ("config", "path"),
}
