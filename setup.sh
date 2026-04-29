#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
info() { echo -e "${DIM}  $1${NC}"; }
ask()  { echo -e "\n${YELLOW}?${NC} $1"; }

echo ""
echo "shade — setup"
echo "============="


# ── 1. Python ─────────────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗${NC} python3 not found. Install it from https://python.org and re-run."
  exit 1
fi
PYTHON=$(command -v python3)
PY_VER=$($PYTHON --version 2>&1)
ok "Python: $PY_VER ($PYTHON)"


# ── 2. Dependencies ───────────────────────────────────────────────────────────

echo ""
echo "Installing dependencies..."
$PYTHON -m pip install --quiet --break-system-packages \
  aiopulse2 resend python-dotenv icalendar pytest 2>/dev/null \
  || $PYTHON -m pip install --quiet aiopulse2 resend python-dotenv icalendar pytest
ok "Dependencies installed"


# ── 3. Environment ────────────────────────────────────────────────────────────

echo ""
echo "Environment (.env)"
echo "------------------"

if [ ! -f "$ENV_FILE" ]; then
  cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
  warn ".env created from .env.example — fill in your values below"
else
  ok ".env exists"
fi

# Load current values
set -a; source "$ENV_FILE"; set +a

prompt_var() {
  local key=$1 prompt=$2 current=$3 secret=${4:-false}
  if [ -n "$current" ]; then
    ok "$key is set"
    return
  fi
  ask "$prompt"
  if [ "$secret" = "true" ]; then
    read -rs value; echo ""
  else
    read -r value
  fi
  if [ -n "$value" ]; then
    # Update or append in .env
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      sed -i '' "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
      echo "${key}=${value}" >> "$ENV_FILE"
    fi
    eval "export ${key}=${value}"
    ok "$key saved"
  else
    warn "$key left blank — edit .env to set it later"
  fi
}

echo ""
echo "Required settings:"
prompt_var "HUB_IP"                   "Hub IP address (e.g. 192.168.1.x):"        "$HUB_IP"
prompt_var "TIMEZONE"                 "Timezone (e.g. America/Los_Angeles):"       "$TIMEZONE"
prompt_var "WEATHER_LAT"              "Latitude (decimal, e.g. 34.0522):"          "$WEATHER_LAT"
prompt_var "WEATHER_LON"              "Longitude (decimal, e.g. -118.2437):"       "$WEATHER_LON"
prompt_var "SCHOOL_CALENDAR_ICS_URL" "School calendar iCal URL:"                  "$SCHOOL_CALENDAR_ICS_URL"

echo ""
echo "Optional — battery alert emails (leave blank to skip):"
info "Requires a free Resend account at https://resend.com"
prompt_var "RESEND_API_KEY" "Resend API key:"        "$RESEND_API_KEY" true
prompt_var "EMAIL_FROM"     "From address:"          "$EMAIL_FROM"
prompt_var "EMAIL_TO"       "To address:"            "$EMAIL_TO"


# ── 4. Shell function ─────────────────────────────────────────────────────────

echo ""
echo "Shell setup"
echo "-----------"

CURRENT_SHELL=$(basename "$SHELL")
SHADE_FN="shade() { $PYTHON $SCRIPT_DIR/shade.py \"\$@\"; }"

if [ "$CURRENT_SHELL" = "zsh" ]; then
  SHELL_FILE="$HOME/.zshrc"
elif [ "$CURRENT_SHELL" = "bash" ]; then
  SHELL_FILE="$HOME/.bashrc"
else
  warn "Unsupported shell: $CURRENT_SHELL"
  info "Add this line manually to your shell config:"
  echo ""
  echo "    $SHADE_FN"
  echo ""
  SHELL_FILE=""
fi

if [ -n "$SHELL_FILE" ]; then
  if grep -q "shade()" "$SHELL_FILE" 2>/dev/null; then
    ok "shade function already in $SHELL_FILE"
  else
    echo "" >> "$SHELL_FILE"
    echo "# shade CLI" >> "$SHELL_FILE"
    echo "$SHADE_FN" >> "$SHELL_FILE"
    ok "shade function added to $SHELL_FILE"
    warn "Run 'source $SHELL_FILE' or open a new terminal to activate"
  fi
fi


# ── 5. Prime caches ───────────────────────────────────────────────────────────

echo ""
echo "Priming caches"
echo "--------------"

set -a; source "$ENV_FILE"; set +a

if [ -n "$SCHOOL_CALENDAR_ICS_URL" ]; then
  echo "Fetching school calendar..."
  $PYTHON "$SCRIPT_DIR/school_calendar.py" && ok "School calendar cached"
else
  warn "SCHOOL_CALENDAR_ICS_URL not set — skipping calendar cache"
fi

if [ -n "$WEATHER_LAT" ] && [ -n "$WEATHER_LON" ]; then
  echo "Fetching weather..."
  $PYTHON -c "
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('$SCRIPT_DIR') / '.env')
from weather import get_weather
w = get_weather(os.environ['WEATHER_LAT'], os.environ['WEATHER_LON'])
print(f\"  Today's high: {w['high_f']}° — Sunset: {w['sunset'].strftime('%I:%M %p')}\")
" && ok "Weather cached" || warn "Weather fetch failed — check WEATHER_LAT/LON in .env"
else
  warn "WEATHER_LAT/WEATHER_LON not set — skipping weather cache"
fi


# ── 6. Done ───────────────────────────────────────────────────────────────────

echo ""
echo "============="
echo -e "${GREEN}Setup complete.${NC}"
echo ""
echo "Next steps:"
echo "  source $SHELL_FILE     # activate the shade command"
echo "  shade list             # verify hub connection"
echo "  shade battery          # check battery levels"
echo ""
