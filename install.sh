#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Petrel"
SERVICE_NAME="Petrel"
REPO_URL="https://github.com/sezgynus/Petrel.git"
INSTALL_USER="${SUDO_USER:-$USER}"
INSTALL_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_REPO_DIR="$INSTALL_HOME/Petrel"
VENV_DIR="$INSTALL_HOME/petrel-env"
APP_CONFIG_DIR="$INSTALL_HOME/.config/Petrel"
ENV_FILE="$APP_CONFIG_DIR/Petrel.env"

if [[ "$REPO_DIR" != "$EXPECTED_REPO_DIR" ]]; then
    echo "Petrel must be cloned to $EXPECTED_REPO_DIR" >&2
    exit 1
fi

if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "$REPO_DIR is not a Git repository." >&2
    exit 1
fi

if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
    echo "The Petrel repository must be clean before installation." >&2
    exit 1
fi

if [[ -n "${MOONRAKER_CONFIG:-}" ]]; then
    MOONRAKER_CONF="$MOONRAKER_CONFIG"
elif [[ -f "$INSTALL_HOME/printer_data/config/moonraker.conf" ]]; then
    MOONRAKER_CONF="$INSTALL_HOME/printer_data/config/moonraker.conf"
elif [[ -f "$INSTALL_HOME/moonraker.conf" ]]; then
    MOONRAKER_CONF="$INSTALL_HOME/moonraker.conf"
else
    echo "Moonraker configuration not found. Set MOONRAKER_CONFIG=/path/to/moonraker.conf and run again." >&2
    exit 1
fi

MOONRAKER_CONFIG_DIR="$(dirname "$MOONRAKER_CONF")"
if [[ "$(basename "$MOONRAKER_CONFIG_DIR")" == "config" ]]; then
    MOONRAKER_DATA_DIR="$(dirname "$MOONRAKER_CONFIG_DIR")"
else
    MOONRAKER_DATA_DIR="$INSTALL_HOME/printer_data"
fi
UPDATE_CONF="$MOONRAKER_CONFIG_DIR/Petrel.conf"
ASVC_FILE="$MOONRAKER_DATA_DIR/moonraker.asvc"

echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y git python3-venv python3-dev build-essential liblgpio-dev swig

echo "Preparing Python environment..."
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    sudo -u "$INSTALL_USER" python3 -m venv "$VENV_DIR"
fi
sudo -u "$INSTALL_USER" "$VENV_DIR/bin/python" -m pip install --upgrade pip
sudo -u "$INSTALL_USER" "$VENV_DIR/bin/python" -m pip install -r "$REPO_DIR/requirements.txt"

echo "Preparing Petrel configuration..."
sudo -u "$INSTALL_USER" mkdir -p "$APP_CONFIG_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "No existing Petrel configuration found."
    echo "Starting first-time configuration..."
    sudo -u "$INSTALL_USER" "$REPO_DIR/configure.sh"
else
    echo "Keeping existing configuration: $ENV_FILE"
    sudo -u "$INSTALL_USER" "$VENV_DIR/bin/python" "$REPO_DIR/tools/env_defaults.py" "$ENV_FILE"
fi

supp_groups=()
for group in dialout gpio; do
    if getent group "$group" >/dev/null; then
        sudo usermod -aG "$group" "$INSTALL_USER"
        supp_groups+=("$group")
    fi
done

SUPPLEMENTARY_LINE=""
if (("${#supp_groups[@]}" > 0)); then
    SUPPLEMENTARY_LINE="SupplementaryGroups=${supp_groups[*]}"
fi

echo "Installing systemd service..."
sed \
    -e "s|@PETREL_USER@|$INSTALL_USER|g" \
    -e "s|@PETREL_HOME@|$INSTALL_HOME|g" \
    -e "s|@SUPPLEMENTARY_GROUPS@|$SUPPLEMENTARY_LINE|g" \
    "$REPO_DIR/Petrel.service" | sudo tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null
sudo systemctl daemon-reload

echo "Registering Moonraker Update Manager..."
cat > "$UPDATE_CONF" <<EOF
[update_manager Petrel]
type: git_repo
channel: dev
path: ~/Petrel
origin: $REPO_URL
primary_branch: master
virtualenv: ~/petrel-env
requirements: requirements.txt
managed_services: Petrel
EOF
chown "$INSTALL_USER:$INSTALL_USER" "$UPDATE_CONF"

INCLUDE_LINE="[include Petrel.conf]"
if ! grep -Fqx "$INCLUDE_LINE" "$MOONRAKER_CONF"; then
    printf '\n%s\n' "$INCLUDE_LINE" >> "$MOONRAKER_CONF"
fi

mkdir -p "$MOONRAKER_DATA_DIR"
touch "$ASVC_FILE"
if ! grep -Fqx "$SERVICE_NAME" "$ASVC_FILE"; then
    printf '%s\n' "$SERVICE_NAME" >> "$ASVC_FILE"
fi
chown "$INSTALL_USER:$INSTALL_USER" "$ASVC_FILE"

sudo systemctl enable --now "$SERVICE_NAME.service"

if systemctl list-unit-files moonraker.service >/dev/null 2>&1; then
    sudo systemctl restart moonraker.service
else
    echo "Moonraker service name was not detected as moonraker.service."
    echo "Restart your Moonraker instance so it loads Petrel.conf and moonraker.asvc."
fi

echo
echo "Petrel installation complete."
echo "Edit: $ENV_FILE"
echo "Service: $SERVICE_NAME.service"
echo "Moonraker updater: [update_manager Petrel]"
