#!/bin/bash

PIP_26="https://bootstrap.pypa.io/2.6/get-pip.py"
PIP="https://bootstrap.pypa.io/get-pip.py"

# Check if pip exists on this server
if ! command -v pip &>/dev/null; then
  # Bootstrap pip it if not present
  PY_VER=$(python -c "import sys; print('2.6' if sys.version_info[0] == 2 and sys.version_info[1] < 7 else '2.7')")
  PIP_URL="$PIP"

  if test PY_VER = "2.6"; then
    PIP_URL="$PIP_26"
  fi

  echo "Pip not found, installing from $PIP_URL"
  curl -O "$PIP_URL"

  if ! python get-pip.py &>/dev/null; then
    echo "Error installing pip"
    rm get-pip.py
    exit 1
  fi

  rm get-pip.py
fi

# Install via zip, git package not required by doing this
if ! pip install --upgrade https://github.com/usajusaj/server-scripts/archive/master.zip; then
  echo "Error installing server-scripts"
  exit 1
fi

INSTALL_DIR=$(python -c "import ccbr_server, os; print(os.path.dirname(ccbr_server.__file__))")
DEFAULT_CONF="$INSTALL_DIR/etc/ccbr_scripts.ini"

if test -f /etc/ccbr_scripts.ini; then
  echo "Config ini exists: /etc/ccbr_scripts.ini"
  echo "Check for new config vars in $DEFAULT_CONF"
else
  echo "Copying default conf from $DEFAULT_CONF to /etc/ccbr_scripts.ini"
  cp "$DEFAULT_CONF" /etc
fi
