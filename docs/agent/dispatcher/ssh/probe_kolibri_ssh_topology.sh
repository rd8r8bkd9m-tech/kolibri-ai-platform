#!/usr/bin/env bash
set -u

targets=(
  kolibri-main
  kolibri-uiap
  kolibri-qjns
  kolibri-9fts
  kolibri-new
  reserve242
  hostvds-highload
  hostvds-agent-01
  hostvds-agent-02
  hostvds-agent-03
  hostvds-agent-04
  hostvds-agent-05
  hostvds-agent-06
  hostvds-agent-07
  hostvds-agent-08
  hostvds-agent-09
  hostvds-paris-highload
  server-kfrm
  kolibri-primary-codex
  kolibri-home
)

ok=0
fail=0
echo "probe_from $(hostname 2>/dev/null || echo unknown) $(id -un 2>/dev/null || echo unknown)"
for target in "${targets[@]}"; do
  out="$(
    ssh \
      -o BatchMode=yes \
      -o PasswordAuthentication=no \
      -o KbdInteractiveAuthentication=no \
      -o PreferredAuthentications=publickey \
      -o ConnectTimeout=6 \
      -o ConnectionAttempts=1 \
      -o StrictHostKeyChecking=accept-new \
      "${target}" 'printf "%s %s" "$(hostname)" "$(id -un)"' 2>&1
  )"
  rc=$?
  if [ "${rc}" -eq 0 ]; then
    ok=$((ok + 1))
    printf 'OK\t%s\t%s\n' "${target}" "${out}"
  else
    fail=$((fail + 1))
    printf 'FAIL\t%s\t%s\n' "${target}" "$(printf '%s' "${out}" | tail -n 1)"
  fi
done
printf 'SUMMARY\tok=%s\tfail=%s\ttotal=%s\n' "${ok}" "${fail}" "$((ok + fail))"
