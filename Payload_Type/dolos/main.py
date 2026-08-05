"""Dolos service entry point.

A Mythic wrapper payload type — no dynamic query monkey-patch needed
(encoder choices are loaded from DOLOS_REMOTE_COMMAND at import time).
"""

import mythic_container

# Importing dolos triggers __init__.py -> auto-imports builder.py
# (only builder.py remains — wrappers have no callback commands).
import dolos  # noqa: F401

mythic_container.mythic_service.start_and_run_forever()