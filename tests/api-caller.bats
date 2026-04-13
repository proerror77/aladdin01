#!/usr/bin/env bats
# tests/api-caller.bats — api-caller.sh regression tests (bats-core)
# No external API calls — pure local logic validation.

SCRIPT="./scripts/api-caller.sh"

setup() {
  # 保存原始环境变量
  _ORIG_ARK="${ARK_API_KEY:-}"
  _ORIG_TUZI="${TUZI_API_KEY:-}"
  _ORIG_IMAGE_URL="${IMAGE_GEN_API_URL:-}"
  _ORIG_IMAGE_KEY="${IMAGE_GEN_API_KEY:-}"
  _ORIG_OPENAI="${OPENAI_API_KEY:-}"
}

teardown() {
  export ARK_API_KEY="$_ORIG_ARK"
  export TUZI_API_KEY="$_ORIG_TUZI"
  export IMAGE_GEN_API_URL="$_ORIG_IMAGE_URL"
  export IMAGE_GEN_API_KEY="$_ORIG_IMAGE_KEY"
  export OPENAI_API_KEY="$_ORIG_OPENAI"
  rm -f /tmp/test_payload.json /tmp/api-caller-curl-count
}

# ── env-check: tuzi fallback ────────────────────────────────────────────────

@test "env-check: TUZI_API_KEY fallback when IMAGE_GEN_API_URL unset" {
  unset IMAGE_GEN_API_URL IMAGE_GEN_API_KEY 2>/dev/null || true
  export ARK_API_KEY="test-key"
  export TUZI_API_KEY="tuzi-key"
  run bash "$SCRIPT" env-check
  [ "$status" -eq 0 ]
  [[ "$output" == *"fallback to tuzi"* ]]
}

@test "env-check: missing both IMAGE_GEN_API_URL and TUZI_API_KEY fails" {
  unset IMAGE_GEN_API_URL IMAGE_GEN_API_KEY TUZI_API_KEY 2>/dev/null || true
  export ARK_API_KEY="test-key"
  run bash "$SCRIPT" env-check
  [ "$status" -ne 0 ]
  [[ "$output" == *"Missing: IMAGE_GEN_API_URL"* ]]
}

# ── env-check: output messages ──────────────────────────────────────────────

@test "env-check: all required set → exit 0" {
  export ARK_API_KEY="test-key"
  export IMAGE_GEN_API_URL="https://example.com"
  export IMAGE_GEN_API_KEY="test-img-key"
  run bash "$SCRIPT" env-check
  [ "$status" -eq 0 ]
  [[ "$output" == *"All required environment variables are set"* ]]
}

@test "env-check: missing ARK_API_KEY → exit 1 with message" {
  unset ARK_API_KEY IMAGE_GEN_API_URL IMAGE_GEN_API_KEY TUZI_API_KEY 2>/dev/null || true
  run bash "$SCRIPT" env-check
  [ "$status" -ne 0 ]
  [[ "$output" == *"Missing: ARK_API_KEY"* ]]
}

# ── env-check: OPENAI_API_KEY optional ──────────────────────────────────────

@test "env-check: OPENAI_API_KEY missing shows Optional, not Missing" {
  unset OPENAI_API_KEY 2>/dev/null || true
  export ARK_API_KEY="test-key"
  export IMAGE_GEN_API_URL="https://example.com"
  export IMAGE_GEN_API_KEY="test-img-key"
  run bash "$SCRIPT" env-check
  [ "$status" -eq 0 ]
  [[ "$output" == *"Optional: OPENAI_API_KEY"* ]]
  # Must NOT contain "Missing: OPENAI_API_KEY"
  [[ "$output" != *"Missing: OPENAI_API_KEY"* ]]
}

# ── image_gen: double-path regression ──────────────────────────────────────

@test "image_gen generate: IMAGE_GEN_API_URL with /v1 suffix no double-path" {
  export ARK_API_KEY="test-key"
  export IMAGE_GEN_API_URL="https://example.com/v1"
  export IMAGE_GEN_API_KEY="test-key"
  echo '{"model":"test","prompt":"test","n":1,"size":"512x512"}' > /tmp/test_payload.json
  # 验证脚本不会崩溃（实际 curl 会失败，但不应是 double-path 导致的）
  run bash -c '
    safe_curl() { echo "URL: $@"; }
    export -f safe_curl
    source ./scripts/api-caller.sh image_gen generate /tmp/test_payload.json 2>&1 || true
  '
  # 确保输出中没有 /v1/v1
  [[ "$output" != */v1/v1* ]]
  rm -f /tmp/test_payload.json
}

@test "seedance create: transport errors are retried instead of exiting immediately" {
  export ARK_API_KEY="test-key"
  export CURL_MAX_RETRIES="3"
  echo '{"prompt":"test"}' > /tmp/test_payload.json

  local stub_dir
  stub_dir="$(mktemp -d)"
  cat > "${stub_dir}/curl" <<'EOF'
#!/usr/bin/env bash
COUNT_FILE="/tmp/api-caller-curl-count"
count=0
if [[ -f "$COUNT_FILE" ]]; then
  count=$(cat "$COUNT_FILE")
fi
count=$((count + 1))
echo "$count" > "$COUNT_FILE"

if [[ "$count" -lt 3 ]]; then
  exit 7
fi

out=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o)
      out="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
printf '{"ok":true}' > "$out"
printf '200'
EOF
  chmod +x "${stub_dir}/curl"

  run env PATH="${stub_dir}:$PATH" bash "$SCRIPT" seedance create /tmp/test_payload.json
  [ "$status" -eq 0 ]
  [[ "$output" == *'"ok":true'* ]]
  [ "$(cat /tmp/api-caller-curl-count)" -eq 3 ]

  rm -rf "$stub_dir"
}
