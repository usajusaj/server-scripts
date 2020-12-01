#!/bin/bash

# Check if pip exists on this server
if ! command -v pip &>/dev/null; then
  # Bootstrap pip it if not present
  echo "Pip not found, installing from https://bootstrap.pypa.io/get-pip.py"
  curl -O https://bootstrap.pypa.io/get-pip.py

  if ! python get-pip.py &>/dev/null; then
    echo "Error installing pip"
    exit 1
  fi
fi

# Install via zip, git package not required by doing this
if ! pip install --upgrade https://github.com/usajusaj/server-scripts/archive/master.zip; then
  echo "Error installing server-scripts"
  exit 1
fi

INSTALL_DIR=$(python -c "import ccbr_server, os; print(os.path.dirname(ccbr_server.__file__))")
DEFAULT_CONF="$INSTALL_DIR/etc/ccbr_scripts.ini"

if test -f /etc/ccbr_scripts.ini
then
  echo "Config ini exists: /etc/ccbr_scripts.ini"
  echo "Check for new config vars in $DEFAULT_CONF"
else
  echo "Copying default conf from $DEFAULT_CONF to /etc/ccbr_scripts.ini"
  cp "$DEFAULT_CONF" /etc
fi
