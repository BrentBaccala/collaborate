#!/bin/bash
# Best-effort: configure the bbb_query Postgres role used by
# bbb-shared-notes.  The setup script is a no-op if BigBlueButton's
# bbb_graphql database is not yet present, so installing this package
# before BBB is harmless — admin can re-run /usr/sbin/bbb-shared-notes-setup
# after BBB install.
/usr/sbin/bbb-shared-notes-setup || true
