#!/bin/bash

###
# This script will help you install any desired locale
#
# Usage:
#
# Installing single locale: bash <(curl -sSL https://raw.githubusercontent.com/stefanpejcic/openpanel-translations/main/install.sh) sr-sr
#
# Installing multiple locales at once: bash <(curl -sSL https://raw.githubusercontent.com/stefanpejcic/openpanel-translations/main/install.sh) sr-sr tr-tr
#
###

# might change in future
github_repo="stefanpejcic/openpanel-translations"

# locales dir since OpenPanel v.0.2.1
babel_translations="/etc/openpanel/openpanel/translations"

# at least 1 locale is needed
if [ "$#" -lt 1 ]; then
  if ! command -v jq &> /dev/null; then
    echo "jq command is required to parse JSON responses. Please install jq to use this feature."
    exit 1
  fi

  echo "Please provide at least one locale to the command, or a list"
  echo ""
  # list available locales from github repo
  echo "Available locales:"
  locales=$(curl -s "https://api.github.com/repos/$github_repo/contents" | jq -r '.[] | select(.type == "dir") | .name')
  echo "$locales"
  echo ""
  echo "Example for a single locale (DE): bash <(curl -sSL https://raw.githubusercontent.com/$github_repo/main/install.sh) de-de"
  echo ""
  echo "Example for multiple locales (DE & ES): bash <(curl -sSL https://raw.githubusercontent.com/$github_repo/main/install.sh) de-de es-es"
  echo ""
  
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
    echo "Installing $formatted_locale locale.."
    echo ""
    pybabel init -i messages.pot -d $babel_translations -l "$formatted_locale"
    wget -O $babel_translations/"$formatted_locale"/LC_MESSAGES/messages.po "https://raw.githubusercontent.com/$github_repo/$formatted_locale/messages.pot"
  else
    echo "Invalid locale format: $locale. Skipping."
  fi
done

# Do this only once
echo "Compiling .mo files for all available locales in $babel_translations directory.."
pybabel compile -f -d $babel_translations
echo "Restarting OpenPanel to apply translations.."
docker restart openpanel
echo "DONE'
