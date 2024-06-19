#!/bin/bash

###
# This script will help you install any desired locale
#
# Usage:
#
# Installing single locale: bash <(curl -sSL https://get.openpanel.co/) sr-sr
#
# Installing multiple locales at once: bash <(curl -sSL https://get.openpanel.co/) sr-sr tr-tr
#
###

# might change in future
github_repo="stefanpejcic/openpanel-translations"

# at least 1 locale is needed
if [ "$#" -lt 1 ]; then
  if ! command -v jq &> /dev/null; then
    echo "jq command is required to parse JSON responses. Please install jq to use this feature."
    exit 1
  fi
  
  # list available locales from github repo
  echo "Available locales:"
  locales=$(curl -s "https://api.github.com/repos/$github_repo/contents" | jq -r '.[] | select(.type == "dir") | .name')
  echo "$locales"
  exit 0
fi

cd /usr/local/panel

validate_locale() {
  # validate format (LL-LL or ll-ll)
  if [[ "$1" =~ ^[a-z]{2}-[a-z]{2}$ ]] || [[ "$1" =~ ^[A-Z]{2}-[A-Z]{2}$ ]]; then
    return 0  # ok
  else
    return 1  # not ok
  fi
}

# Loop through each provided locale
for locale in "$@"
do
  # must be lowercase
  formatted_locale=$(echo "$locale" | tr '[:upper:]' '[:lower:]')

  if validate_locale "$formatted_locale"; then
    pybabel init -i messages.pot -d /etc/openpanel/openpanel/translations -l "$formatted_locale"
    wget -O /etc/openpanel/openpanel/translations/"$formatted_locale"/LC_MESSAGES/messages.po "https://raw.githubusercontent.com/$github_repo/$formatted_locale/messages.pot"
  else
    echo "Invalid locale format: $locale. Skipping."
  fi
done

# Do this only once
pybabel compile -f -d /etc/openpanel/openpanel/translations
docker restart openpanel
