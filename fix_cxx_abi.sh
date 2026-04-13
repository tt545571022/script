#!/bin/bash

set -euo pipefail

TARGET_FILE="/usr/local/Ascend/nnal/atb/set_env.sh"
OLD_TEXT='    cxx_abi=""'
NEW_TEXT='    cxx_abi="1"'

if [[ ! -f "$TARGET_FILE" ]]; then
    echo "Target file not found: $TARGET_FILE" >&2
    exit 1
fi

if grep -Fq "$NEW_TEXT" "$TARGET_FILE"; then
    echo "Already updated: $TARGET_FILE"
    exit 0
fi

if ! grep -Fq "$OLD_TEXT" "$TARGET_FILE"; then
    echo "Expected text not found in $TARGET_FILE" >&2
    exit 1
fi

sed -i 's|    cxx_abi=""|    cxx_abi="1"|' "$TARGET_FILE"
echo "Updated: $TARGET_FILE"