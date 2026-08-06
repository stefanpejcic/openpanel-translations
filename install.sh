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
babel_translations="/etc/openpanel/openpanel/translations"

if [ "$#" -lt 1 ]; then
    if ! command -v jq >/dev/null 2>&1; then
        echo "jq is required to list available locales."
        exit 1
    fi

    echo "Please provide at least one locale."
    echo
    echo "Available locales:"
    curl -s "https://api.github.com/repos/$github_repo/contents" \
        | jq -r '.[] | select(.type=="dir" and (.name|test("^\\.")|not)) | .name'
    echo
    echo "Example:"
    echo "  opencli locale de-de"
    echo "  opencli locale de-de es-es"
    exit 0
fi

validate_locale() {
    [[ "$1" =~ ^[a-z]{2}-[a-z]{2}$ ]]
}

if command -v docker >/dev/null 2>&1; then
    CONTAINER_CMD="docker"
elif command -v podman >/dev/null 2>&1; then
    CONTAINER_CMD="podman"
else
    echo "Error: neither docker nor podman found."
    exit 1
fi

for locale in "$@"; do
    formatted_locale=$(echo "$locale" | tr '[:upper:]' '[:lower:]')

    if ! validate_locale "$formatted_locale"; then
        echo "Invalid locale format: $locale. Skipping."
        continue
    fi

    two_letter="${formatted_locale%%-*}"

    echo "Creating directory for $formatted_locale..."
    mkdir -p "$babel_translations/$two_letter/LC_MESSAGES"

    echo "Downloading locale..."
    if ! wget -q -O "$babel_translations/$two_letter/LC_MESSAGES/messages.po" \
        "https://raw.githubusercontent.com/$github_repo/main/$formatted_locale/messages.po"; then
        echo "Failed to download $formatted_locale"
        continue
    fi

    $CONTAINER_CMD exec openpanel pybabel update -i "$babel_translations/$two_letter/LC_MESSAGES/messages.po" -d "$babel_translations" -l "$two_letter" >/dev/null 2>&1
    echo
done


if [ "$CONTAINER_CMD" = "docker" ]; then
    echo "Compiling .mo files..."
    docker exec openpanel pybabel compile -f -d "$babel_translations" >/dev/null 2>&1
fi

echo "Flushing cache..."
docker exec openpanel_redis redis-cli DEL openpanel_cache_app.get_available_locales_memver >/dev/null 2>&1


echo "DONE"
