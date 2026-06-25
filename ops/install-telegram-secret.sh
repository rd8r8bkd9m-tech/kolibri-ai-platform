#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_SSH_ALIAS="${CONTROL_PLANE_SSH_ALIAS:-kolibri-main-api}"

if [[ "${CONTROL_PLANE_SSH_ALIAS}" == "kolibri-main-api" ]]; then
  SSH_TARGET=(ssh -tt -J kolibri-home root@10.99.0.2)
else
  SSH_TARGET=(ssh -tt "${CONTROL_PLANE_SSH_ALIAS}")
fi

"${SSH_TARGET[@]}" '
  set -euo pipefail
  install -d -m 700 /etc/kolibri
  bash -c '"'"'
    set -euo pipefail
    umask 077
    read -rsp "Telegram bot token: " TOKEN
    echo
    printf "TELEGRAM_BOT_TOKEN=%s\n" "$TOKEN" > /etc/kolibri/telegram.env
    chmod 600 /etc/kolibri/telegram.env
    unset TOKEN
    echo TELEGRAM_SECRET_STORED
  '"'"'
'
