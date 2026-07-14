#!/usr/bin/env bash
set -euo pipefail

repo="${1:-fakecat/alicer}"
key_properties="android/key.properties"
keystore_file="android/upload-keystore.p12"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated" >&2
  exit 1
fi

if [[ ! -f "$key_properties" || ! -f "$keystore_file" ]]; then
  echo "Missing android/key.properties or android/upload-keystore.p12" >&2
  exit 1
fi

read_prop() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1)}' "$key_properties"
}

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    echo "Missing environment variable: $key" >&2
    exit 1
  fi
}

for key in COS_BUCKET COS_REGION COS_SECRET_ID COS_SECRET_KEY; do
  require_env "$key"
done

base64 -w 0 "$keystore_file" | gh secret set ALICER_UPLOAD_KEYSTORE_BASE64 --repo "$repo"
read_prop storePassword | gh secret set ALICER_UPLOAD_STORE_PASSWORD --repo "$repo"
read_prop keyAlias | gh secret set ALICER_UPLOAD_KEY_ALIAS --repo "$repo"
read_prop keyPassword | gh secret set ALICER_UPLOAD_KEY_PASSWORD --repo "$repo"

printf '%s' "$COS_BUCKET" | gh secret set COS_BUCKET --repo "$repo"
printf '%s' "$COS_REGION" | gh secret set COS_REGION --repo "$repo"
printf '%s' "$COS_SECRET_ID" | gh secret set COS_SECRET_ID --repo "$repo"
printf '%s' "$COS_SECRET_KEY" | gh secret set COS_SECRET_KEY --repo "$repo"

echo "GitHub secrets configured for $repo"
