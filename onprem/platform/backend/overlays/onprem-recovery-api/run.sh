#!/bin/sh
set -eu
nginx -c /etc/recovery-proxy/nginx.conf -g 'daemon off;' &
nginx_pid=$!
trap 'kill -QUIT "$nginx_pid" 2>/dev/null || true; wait "$nginx_pid" || true; exit 0' TERM INT
last="$(sha256sum /etc/recovery-tls/tls.crt /etc/recovery-tls/tls.key)"
while kill -0 "$nginx_pid" 2>/dev/null; do
  sleep 10 &
  wait "$!" || true
  # Secret 갱신은 디렉토리 mount로 받는다. subPath를 사용하지 않는다.
  current="$(sha256sum /etc/recovery-tls/tls.crt /etc/recovery-tls/tls.key 2>/dev/null || true)"
  if [ -n "$current" ] && [ "$current" != "$last" ]; then
    if nginx -t -c /etc/recovery-proxy/nginx.conf; then
      kill -HUP "$nginx_pid"
      last="$current"
    fi
  fi
done
wait "$nginx_pid"
