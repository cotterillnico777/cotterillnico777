#!/usr/bin/env bash
# Einrichtung eines frischen Ubuntu-Servers (22.04 / 24.04) für quantbot im PAPER-Modus.
#
# Aufruf auf dem Server als root:
#   curl -fsSL https://raw.githubusercontent.com/cotterillnico777/cotterillnico777/claude/hopeful-goldberg-w1ms4b/deploy/setup_server.sh -o setup_server.sh
#   bash setup_server.sh
#
# Was passiert:
#   - Benutzer "quantbot" ohne Root-Rechte, Bot läuft nur unter diesem Benutzer
#   - Firewall: nur SSH erlaubt, Passwort-Login per SSH aus (nur Schlüssel)
#   - automatische Sicherheitsupdates, Zeitsynchronisation (wichtig für Kerzenschluss)
#   - Repository + Python-Umgebung unter /home/quantbot/cotterillnico777
#   - systemd-Dienst "quantbot-paper": startet beim Booten und nach Abstürzen neu
#
# Es werden KEINE API-Schlüssel benötigt oder abgefragt. LIVE wird nicht aktiviert.
# Das Skript kann gefahrlos mehrfach ausgeführt werden.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/cotterillnico777/cotterillnico777.git}"
BRANCH="${BRANCH:-claude/hopeful-goldberg-w1ms4b}"
BOT_USER="quantbot"
APP_DIR="/home/${BOT_USER}/cotterillnico777"
CONFIG="${CONFIG:-configs/paper_ensemble_4h.yaml}"

if [[ $EUID -ne 0 ]]; then
  echo "Bitte als root ausführen (z. B. nach 'ssh root@SERVER-IP')." >&2
  exit 1
fi

echo "==> Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git python3 python3-venv python3-pip sqlite3 ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python ${PYV} ist zu alt (benötigt 3.11+). Bitte Ubuntu 24.04 verwenden." >&2
  exit 1
fi

echo "==> Zeitsynchronisation"
timedatectl set-ntp true || true
timedatectl set-timezone UTC || true

echo "==> Benutzer ${BOT_USER}"
if ! id "${BOT_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${BOT_USER}"
fi
# SSH-Schlüssel von root übernehmen, damit 'ssh quantbot@SERVER' funktioniert
if [[ -f /root/.ssh/authorized_keys ]]; then
  install -d -m 700 -o "${BOT_USER}" -g "${BOT_USER}" "/home/${BOT_USER}/.ssh"
  install -m 600 -o "${BOT_USER}" -g "${BOT_USER}" /root/.ssh/authorized_keys "/home/${BOT_USER}/.ssh/authorized_keys"
fi

echo "==> SSH absichern (nur Schlüssel, kein Passwort)"
if [[ -s /root/.ssh/authorized_keys ]]; then
  install -d /etc/ssh/sshd_config.d
  cat > /etc/ssh/sshd_config.d/90-quantbot.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
else
  echo "    WARNUNG: kein SSH-Schlüssel für root gefunden – Passwort-Login bleibt an." >&2
fi

echo "==> Firewall (nur SSH)"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null

echo "==> Repository"
if [[ -d "${APP_DIR}/.git" ]]; then
  sudo -u "${BOT_USER}" git -C "${APP_DIR}" fetch -q origin "${BRANCH}"
  sudo -u "${BOT_USER}" git -C "${APP_DIR}" checkout -q "${BRANCH}"
  sudo -u "${BOT_USER}" git -C "${APP_DIR}" pull -q --ff-only origin "${BRANCH}"
else
  sudo -u "${BOT_USER}" git clone -q --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Python-Umgebung"
sudo -u "${BOT_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${BOT_USER}" "${APP_DIR}/.venv/bin/pip" install -q --upgrade pip
sudo -u "${BOT_USER}" "${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"
sudo -u "${BOT_USER}" install -d -m 700 "${APP_DIR}/state"

# Dienste: Hauptinstanz (0,5 % Risiko) und Vergleichsinstanz (1 % Risiko), je eigenes Spielkonto
declare -A UNITS=(
  [quantbot-paper]="${CONFIG}"
  [quantbot-paper-risk1]="${CONFIG_RISK1:-configs/paper_ensemble_4h_risk1.yaml}"
)

echo "==> Selbsttest (Konfigurationen laden, keine Orders)"
for unit in "${!UNITS[@]}"; do
  cfg="${UNITS[$unit]}"
  sudo -u "${BOT_USER}" bash -c "cd '${APP_DIR}' && .venv/bin/python -c \"from quantbot.config import load_config; c=load_config('${cfg}'); assert not c.live.enabled; print('    ${unit}: ok', [s.name for s in c.strategies], 'Risiko', c.risk.risk_per_trade)\""
done

echo "==> systemd-Dienste"
for unit in "${!UNITS[@]}"; do
  sed -e "s#@APP_DIR@#${APP_DIR}#g" -e "s#@USER@#${BOT_USER}#g" -e "s#@CONFIG@#${UNITS[$unit]}#g" \
    "${APP_DIR}/deploy/quantbot-paper.service" > "/etc/systemd/system/${unit}.service"
done
install -m 755 "${APP_DIR}/deploy/qb" /usr/local/bin/qb
systemctl daemon-reload
systemctl enable "${!UNITS[@]}" >/dev/null

cat <<EOF

Fertig. Zwei Dienste sind eingerichtet, aber noch NICHT gestartet:
  quantbot-paper        (0,5 % Risiko, Befehle: qb ...)
  quantbot-paper-risk1  (1 % Risiko,   Befehle: qb risk1 ...)

Nächste Schritte (siehe docs/SERVER.md):
  1. Paper-Bot auf dem Mac stoppen (Ctrl+C) und das Journal hochladen:
       scp state/quantbot_paper.sqlite quantbot@SERVER-IP:cotterillnico777/state/
     (ohne Upload startet ein neues Paper-Konto mit 10.000)
     und genauso für die 1-%-Instanz (falls sie auf dem Mac lief):
       scp state/risk1_paper.sqlite* quantbot@SERVER-IP:cotterillnico777/state/
  2. Starten:   qb start        und   qb risk1 start
  3. Prüfen:    qb status       und   qb risk1 status
EOF
