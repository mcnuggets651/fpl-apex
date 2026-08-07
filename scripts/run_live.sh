#!/usr/bin/env sh
set -eu
apex-fpl run --scenario both --horizon "${APEX_HORIZON:-6}" --force
