#!/usr/bin/env bash

# Portable defaults; caller-provided environment variables take precedence.
_wb_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [ ! -d "$_wb_dir/worldbridge" ] && [ "$_wb_dir" != / ]; do
    _wb_dir=$(dirname -- "$_wb_dir")
done
WORLDBRIDGE_ROOT=${WORLDBRIDGE_ROOT:-$_wb_dir}
WORLDBRIDGE_EXTERNAL=${WORLDBRIDGE_EXTERNAL:-$WORLDBRIDGE_ROOT/external}
WORLDBRIDGE_MODELS=${WORLDBRIDGE_MODELS:-$WORLDBRIDGE_ROOT/models}
WORLDBRIDGE_CACHE=${WORLDBRIDGE_CACHE:-$WORLDBRIDGE_ROOT/.cache}
WORLDBRIDGE_PYTHON=${WORLDBRIDGE_PYTHON:-python}
WORLDBRIDGE_SITE_PACKAGES=${WORLDBRIDGE_SITE_PACKAGES:-$WORLDBRIDGE_EXTERNAL/site-packages}
BLENDER_BIN=${BLENDER_BIN:-blender}
BLENDER_RESOURCES=${BLENDER_RESOURCES:-$WORLDBRIDGE_EXTERNAL/blender/resources}
export WORLDBRIDGE_ROOT WORLDBRIDGE_EXTERNAL WORLDBRIDGE_MODELS WORLDBRIDGE_CACHE
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-${WORLDBRIDGE_ROOT}/infinigen}"
TVNC_ROOT="${TVNC_ROOT:-${WORLDBRIDGE_EXTERNAL}/turbovnc/extracted/opt/TurboVNC}"
RUNTIME_DIR="${RUNTIME_DIR:-${WORLDBRIDGE_EXTERNAL}/turbovnc/runtime}"
DISPLAY_NUM="${DISPLAY_NUM:-1}"
GEOMETRY="${GEOMETRY:-1920x1080}"
DEPTH="${DEPTH:-24}"
DIRECT="${DIRECT:-0}"

mkdir -p \
  "$RUNTIME_DIR/home" \
  "$RUNTIME_DIR/home/Desktop" \
  "$RUNTIME_DIR/home/Downloads" \
  "$RUNTIME_DIR/home/Documents" \
  "$RUNTIME_DIR/tmp" \
  "$RUNTIME_DIR/logs" \
  "$RUNTIME_DIR/home/.vnc" \
  "$RUNTIME_DIR/config" \
  "$RUNTIME_DIR/cache" \
  "$RUNTIME_DIR/run"
chmod 700 "$RUNTIME_DIR/run"

export HOME="$RUNTIME_DIR/home"
export TMPDIR="$RUNTIME_DIR/tmp"
export PATH="$TVNC_ROOT/bin:$PATH"

XSTARTUP="$RUNTIME_DIR/xstartup-unity-hub.sh"
APP_LOG="$RUNTIME_DIR/logs/xstartup-apps.log"
cat > "$XSTARTUP" <<EOF
#!/usr/bin/env bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export ROOT_DIR="$ROOT_DIR"
export UNITY_ROOT="${WORLDBRIDGE_EXTERNAL}/unity"
export EXPORT_DIR="$ROOT_DIR/outputs/urban_block_10/unity_export"
export RUNTIME_DIR="$ROOT_DIR/outputs/urban_block_10/unity_export/unity_runtime"
export XDG_CONFIG_HOME="${WORLDBRIDGE_EXTERNAL}/turbovnc/runtime/config"
export XDG_CACHE_HOME="${WORLDBRIDGE_EXTERNAL}/turbovnc/runtime/cache"
export XDG_RUNTIME_DIR="${WORLDBRIDGE_EXTERNAL}/turbovnc/runtime/run"
export XDG_DATA_DIRS="/usr/local/share:/usr/share"
export XDG_SESSION_TYPE="x11"
export XDG_CURRENT_DESKTOP="ubuntu:GNOME"
export GNOME_SHELL_SESSION_MODE="ubuntu"
export GSETTINGS_BACKEND="dconf"
export NO_AT_BRIDGE=1
export LIBGL_ALWAYS_SOFTWARE=1
mkdir -p "\$XDG_CONFIG_HOME" "\$XDG_CACHE_HOME" "\$XDG_RUNTIME_DIR"
chmod 700 "\$XDG_RUNTIME_DIR"

cd "$ROOT_DIR"
dbus-run-session -- bash -lc '
  xmodmap -e "remove mod4 = Super_L Super_R Hyper_L" \
          -e "remove mod1 = Meta_L Meta_R" \
          -e "keysym Super_L = Control_L" \
          -e "keysym Super_R = Control_R" \
          -e "keysym Meta_L = Control_L" \
          -e "keysym Meta_R = Control_R" \
          -e "add control = Control_L Control_R" >> "$APP_LOG" 2>&1 || true

  gsettings set org.gnome.Terminal.Legacy.Keybindings:/org/gnome/terminal/legacy/keybindings/ copy "<Control>c" >> "$APP_LOG" 2>&1 || true
  gsettings set org.gnome.Terminal.Legacy.Keybindings:/org/gnome/terminal/legacy/keybindings/ paste "<Control>v" >> "$APP_LOG" 2>&1 || true

  gnome-shell --x11 --replace >> "$APP_LOG" 2>&1 &
  sleep 5

  gnome-terminal -- bash -lc "
    cd \"$ROOT_DIR\"
    echo \"GNOME desktop is running on DISPLAY=\$DISPLAY\"
    echo
    echo \"Unity Hub should open automatically. If it does not, run:\"
    echo \"  scripts/launch_unity_hub_controlled.sh\"
    echo
    echo \"After logging into Unity Hub and activating Personal license:\"
    echo \"  scripts/render_unity_urban_block10.sh\"
    echo
    exec bash
  " >> "$APP_LOG" 2>&1 &

  scripts/launch_unity_hub_controlled.sh >> "$APP_LOG" 2>&1 &

  while true; do
    sleep 3600
  done
'
EOF
chmod +x "$XSTARTUP"

VNC_ARGS=(
  ":$DISPLAY_NUM"
  -geometry "$GEOMETRY"
  -depth "$DEPTH"
  -noautokill
  -xstartup "$XSTARTUP"
  -log "$RUNTIME_DIR/logs/vnc-:$DISPLAY_NUM.log"
)

if [[ "$DIRECT" == "1" ]]; then
  VNC_ARGS+=(-securitytypes vnc -rfbauth "$RUNTIME_DIR/home/.vnc/passwd")
else
  VNC_ARGS+=(-localhost -securitytypes None)
fi

"$TVNC_ROOT/bin/vncserver" "${VNC_ARGS[@]}"

cat <<EOF
TurboVNC started on display :$DISPLAY_NUM

Connect from your local machine with SSH tunnel:

  ssh -L 590$DISPLAY_NUM:localhost:590$DISPLAY_NUM anonymous@<server-address>

Then open your VNC Viewer to:

  localhost:590$DISPLAY_NUM

If you started with DIRECT=1, connect your VNC Viewer directly to:

  10.130.138.44:590$DISPLAY_NUM

Inside the VNC desktop, Unity Hub should start automatically. If it does not,
run this in the xterm inside VNC:

  cd "$ROOT_DIR"
  scripts/launch_unity_hub_controlled.sh
EOF
