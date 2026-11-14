#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="$(id -un)"
VENV_DIR="$APP_DIR/.venv"
CONFIG_DIR="$HOME/.config/mytube"
ENV_FILE="$CONFIG_DIR/mytube.env"
SERVICE_NAME="mytube"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
DEFAULT_STORAGE_ROOT="/media/devmon/EXTERNAL"

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

prompt_default() {
    local label="$1" default="$2" variable="$3" answer
    read -r -p "$label [$default]: " answer
    printf -v "$variable" '%s' "${answer:-$default}"
}

read_env_value() {
    local key="$1"
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); gsub(/^"/, ""); gsub(/"$/, ""); print; exit }' "$ENV_FILE"
}

[[ "$(uname -s)" == "Linux" ]] || die "Run this script on Linux."
[[ "$EUID" -ne 0 ]] || die "Run as your normal user; the script uses sudo only to install the systemd service."
[[ -d /run/systemd/system ]] || die "A running systemd installation is required."
command -v sudo >/dev/null 2>&1 || die "sudo is required to install and start the systemd service."
command -v python3 >/dev/null 2>&1 || die "Install Python 3 before running this script."
[[ -f "$APP_DIR/requirements.txt" && -f "$APP_DIR/backend/main.py" ]] || die "Run this from a complete MyTube folder."

for path in "$APP_DIR" "$HOME" "$CONFIG_DIR"; do
    [[ "$path" != *[[:space:]]* ]] || die "Paths containing spaces are not supported by this systemd setup: $path"
done

sudo -v

if [[ ! -f "$ENV_FILE" ]]; then
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"

    prompt_default "Jellyfin URL" "${JELLYFIN_URL:-http://127.0.0.1:8096}" JELLYFIN_URL
    prompt_default "Storage root for the database" "${MYTUBE_STORAGE_ROOT:-$DEFAULT_STORAGE_ROOT}" STORAGE_ROOT
    prompt_default "Local media directory" "${MYTUBE_REMOTE_MEDIA_DIR:-$STORAGE_ROOT/yt_video}" MEDIA_DIR
    prompt_default "MyTube bind address" "${MYTUBE_HOST:-0.0.0.0}" MYTUBE_HOST
    prompt_default "MyTube port" "${MYTUBE_PORT:-8000}" MYTUBE_PORT

    JELLYFIN_API_KEY="${JELLYFIN_API_KEY:-}"
    if [[ -z "$JELLYFIN_API_KEY" ]]; then
        read -r -s -p "Jellyfin API key (leave blank to use the config default): " JELLYFIN_API_KEY
        printf '\n'
    fi

    [[ "$JELLYFIN_URL" =~ ^https?://[^[:space:]]+$ ]] || die "Jellyfin URL must start with http:// or https:// and contain no spaces."
    [[ "$STORAGE_ROOT" == /* && "$MEDIA_DIR" == /* ]] || die "Storage root and media directory must be absolute paths."
    [[ "$STORAGE_ROOT" != *[[:space:]]* && "$MEDIA_DIR" != *[[:space:]]* ]] || die "Storage paths cannot contain spaces."
    [[ "$MYTUBE_HOST" != *[[:space:]]* ]] || die "Bind address cannot contain spaces."
    [[ "$MYTUBE_PORT" =~ ^[0-9]+$ ]] && (( MYTUBE_PORT >= 1 && MYTUBE_PORT <= 65535 )) || die "Port must be between 1 and 65535."
    [[ "$JELLYFIN_API_KEY" != *$'\n'* ]] || die "API key cannot contain a newline."

    (
        umask 077
        {
            printf 'JELLYFIN_URL=%s\n' "$JELLYFIN_URL"
            [[ -z "$JELLYFIN_API_KEY" ]] || printf 'JELLYFIN_API_KEY=%s\n' "$JELLYFIN_API_KEY"
            printf 'MYTUBE_STORAGE_ROOT=%s\n' "$STORAGE_ROOT"
            printf 'MYTUBE_REMOTE_MEDIA_DIR=%s\n' "$MEDIA_DIR"
            printf 'MYTUBE_HOST=%s\n' "$MYTUBE_HOST"
            printf 'MYTUBE_PORT=%s\n' "$MYTUBE_PORT"
        } > "$ENV_FILE"
    )
    chmod 600 "$ENV_FILE"
else
    chmod 600 "$ENV_FILE"
    printf 'Keeping existing configuration: %s\n' "$ENV_FILE"
fi

STORAGE_ROOT="$(read_env_value MYTUBE_STORAGE_ROOT)"
MEDIA_DIR="$(read_env_value MYTUBE_REMOTE_MEDIA_DIR)"
MYTUBE_HOST="$(read_env_value MYTUBE_HOST)"
MYTUBE_PORT="$(read_env_value MYTUBE_PORT)"
STORAGE_ROOT="${STORAGE_ROOT:-$DEFAULT_STORAGE_ROOT}"
MEDIA_DIR="${MEDIA_DIR:-$STORAGE_ROOT}"
MYTUBE_HOST="${MYTUBE_HOST:-0.0.0.0}"
MYTUBE_PORT="${MYTUBE_PORT:-8000}"

[[ "$STORAGE_ROOT" == /* && "$MEDIA_DIR" == /* ]] || die "Storage paths in $ENV_FILE must be absolute."
[[ "$STORAGE_ROOT" != *[[:space:]]* && "$MEDIA_DIR" != *[[:space:]]* ]] || die "Storage paths cannot contain spaces."
[[ -d "$STORAGE_ROOT" && -w "$STORAGE_ROOT" ]] || die "Storage root must exist and be writable by $APP_USER: $STORAGE_ROOT"
[[ -d "$MEDIA_DIR" && -r "$MEDIA_DIR" && -w "$MEDIA_DIR" ]] || die "Media directory must exist and be readable and writable: $MEDIA_DIR"
[[ "$MYTUBE_PORT" =~ ^[0-9]+$ ]] && (( MYTUBE_PORT >= 1 && MYTUBE_PORT <= 65535 )) || die "Port in $ENV_FILE must be between 1 and 65535."

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR" || die "Could not create the virtual environment. Install your distribution's python3-venv package."
fi

"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

SERVICE_TMP="$(mktemp)"
trap 'rm -f "$SERVICE_TMP"' EXIT
cat > "$SERVICE_TMP" <<EOF
[Unit]
Description=MyTube
After=network-online.target
Wants=network-online.target
RequiresMountsFor=$STORAGE_ROOT $MEDIA_DIR

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1
UMask=0077
ExecStart=$VENV_DIR/bin/uvicorn backend.main:app --host \${MYTUBE_HOST} --port \${MYTUBE_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo install -o root -g root -m 0644 "$SERVICE_TMP" "$SERVICE_FILE"
sudo systemctl daemon-reload
if ! sudo systemctl enable --now "$SERVICE_NAME.service"; then
    sudo journalctl -u "$SERVICE_NAME.service" -n 50 --no-pager || true
    die "Could not start MyTube. Check the service log above."
fi

printf '\nMyTube is enabled and running as %s.\n' "$APP_USER"
printf 'Configuration: %s\n' "$ENV_FILE"
printf 'Service status: sudo systemctl status %s\n' "$SERVICE_NAME"
printf 'Service logs:   sudo journalctl -u %s -f\n' "$SERVICE_NAME"
printf 'Restart:        sudo systemctl restart %s\n' "$SERVICE_NAME"
printf 'Web port:       %s (open it in your firewall if needed)\n' "$MYTUBE_PORT"
