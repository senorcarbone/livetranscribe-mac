# Shared helpers for the local translation server. Sourced, not executed.

lt_llm_start() {   # $1=model  $2=port  $3=logfile
  local model="$1" port="$2" log="$3" i=0
  llama-server -m "$model" --host 127.0.0.1 --port "$port" \
    -c 4096 -ngl 99 --no-webui > "$log" 2>&1 &
  LLM_PID=$!
  until curl -sf "http://127.0.0.1:$port/health" 2>/dev/null | grep -q 'ok'; do
    kill -0 "$LLM_PID" 2>/dev/null || { echo "llama-server exited — see $log" >&2; return 1; }
    i=$((i+1))
    [ "$i" -gt 600 ] && { echo "llama-server did not become ready — see $log" >&2; return 1; }
    sleep 0.5
  done
  return 0
}

lt_llm_stop() {
  [ -n "${LLM_PID:-}" ] && kill "$LLM_PID" 2>/dev/null
  [ -n "${LLM_PID:-}" ] && wait "$LLM_PID" 2>/dev/null
  return 0
}
