#!/bin/bash
###
# Install desired locale for OpenPanel UI
#
# Usage:
#
# Installing single locale:
#   opencli locale sr-rs
#
# Installing multiple locales at once:
#   opencli locale sr-rs tr-tr
#
###

github_repo="stefanpejcic/openpanel-translations"
translations_dir="/etc/openpanel/openpanel/translations"
cache_key="openpanel_cache_app.get_available_locales"

if [ "$#" -lt 1 ]; then
    if ! command -v jq >/dev/null 2>&1; then
        echo "jq is required to list available locales."
        exit 1
    fi

    echo "Please provide at least one locale."
    echo
    echo "Available locales:"
    curl -s "https://api.github.com/repos/$github_repo/contents" | jq -r '.[] | select(.type=="dir" and (.name|test("^[a-z]{2}-[a-z]{2}$"))) | .name'
    echo
    echo "Example:"
    echo "  opencli locale de-de"
    echo "  opencli locale de-de es-es"
    exit 0
fi

validate_locale() {
    [[ "$1" =~ ^[a-z]{2}-[a-z]{2}$ ]]
}

failed=0
installed=0

for locale in "$@"; do
    formatted_locale=$(echo "$locale" | tr '[:upper:]' '[:lower:]')

    if ! validate_locale "$formatted_locale"; then
        echo "Invalid locale format: $locale. Skipping."
        failed=1
        continue
    fi

    two_letter="${formatted_locale%%-*}"
    target_dir="$translations_dir/$two_letter/LC_MESSAGES"

    echo "Downloading $formatted_locale..."
    tmp_file=$(mktemp)
    if ! wget -q -O "$tmp_file" "https://raw.githubusercontent.com/$github_repo/main/$formatted_locale/messages.po" || [ ! -s "$tmp_file" ]; then
        echo "Failed to download $formatted_locale"
        rm -f "$tmp_file"
        failed=1
        continue
    fi
    mkdir -p "$target_dir"
    mv "$tmp_file" "$target_dir/messages.po"
    chmod 644 "$target_dir/messages.po"

    installed=1
    echo
done

if [ "$installed" -eq 1 ]; then
    echo "Flushing cache..."
    if command -v podman >/dev/null 2>&1; then
        podman exec openpanel_redis redis-cli DEL "$cache_key" >/dev/null 2>&1
    fi
fi

if [ "$failed" -eq 1 ]; then
    echo "DONE with errors"
    exit 1
fi

echo "DONE"
