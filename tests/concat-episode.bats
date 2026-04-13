#!/usr/bin/env bats
# tests/concat-episode.bats — concat-episode.sh regression tests (bats-core)
# Uses ffmpeg/ffprobe stubs to avoid real media processing.

SCRIPT="./scripts/concat-episode.sh"

setup() {
  TEST_DIR="$(mktemp -d)"
  # Create stub bin dir and prepend to PATH
  STUB_BIN="${TEST_DIR}/bin"
  mkdir -p "$STUB_BIN"

  # Default ffprobe stub: reports audio present
  cat > "${STUB_BIN}/ffprobe" << 'STUB'
#!/usr/bin/env bash
# Parse args to decide behavior
for arg in "$@"; do
  if [[ "$arg" == "-select_streams" ]]; then
    SELECT_STREAM="next"
    continue
  fi
  if [[ "${SELECT_STREAM:-}" == "next" ]]; then
    if [[ "$arg" == "a" ]]; then
      # Audio stream query — check FFPROBE_HAS_AUDIO env
      if [[ "${FFPROBE_HAS_AUDIO:-1}" == "0" ]]; then
        exit 0  # no output = no audio
      else
        echo "codec_name=aac"
        exit 0
      fi
    fi
    SELECT_STREAM=""
    continue
  fi
  if [[ "$arg" == "-show_entries" ]]; then
    SHOW_ENTRIES="next"
    continue
  fi
  if [[ "${SHOW_ENTRIES:-}" == "next" ]]; then
    if [[ "$arg" == "format=duration" ]]; then
      echo "42.5"
      exit 0
    fi
    SHOW_ENTRIES=""
    continue
  fi
done
# Fallback: show_streams with no select
echo "codec_name=aac"
STUB
  chmod +x "${STUB_BIN}/ffprobe"

  # Default ffmpeg stub: just copy input to output
  cat > "${STUB_BIN}/ffmpeg" << 'STUB'
#!/usr/bin/env bash
# Find -o flag and create the output file, or find concat output
OUTPUT=""
PREV=""
for arg in "$@"; do
  if [[ "$PREV" == "-o" ]]; then
    OUTPUT="$arg"
  fi
  # concat mode: output is last positional arg before -y
  PREV="$arg"
done
if [[ -n "$OUTPUT" ]]; then
  echo "stub-video-content" > "$OUTPUT"
fi
# Also handle: ffmpeg ... output.mp4 -y
for arg in "$@"; do
  if [[ "$arg" == *.mp4 ]] && [[ "$arg" != *"concat.txt"* ]] && [[ "$arg" != *"shot-"* ]] && [[ ! -f "$arg" ]]; then
    echo "stub-video-content" > "$arg"
  fi
done
exit 0
STUB
  chmod +x "${STUB_BIN}/ffmpeg"

  # du stub
  cat > "${STUB_BIN}/du" << 'STUB'
#!/usr/bin/env bash
echo "1.2M	$2"
STUB
  chmod +x "${STUB_BIN}/du"

  # realpath stub (some CI may not have it)
  if ! command -v realpath &>/dev/null; then
    cat > "${STUB_BIN}/realpath" << 'STUB'
#!/usr/bin/env bash
echo "$1"
STUB
    chmod +x "${STUB_BIN}/realpath"
  fi

  export PATH="${STUB_BIN}:${PATH}"
}

teardown() {
  rm -rf "$TEST_DIR"
  # Clean up any outputs we created
  rm -rf "outputs/test-ep"
  rm -rf "projects/demo"
}

# ── empty directory error ───────────────────────────────────────────────────

@test "concat: no ep_id arg → exit 1 with usage" {
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Usage:"* ]]
}

@test "concat: invalid ep_id → exit 1" {
  run bash "$SCRIPT" "../evil"
  [ "$status" -eq 1 ]
  [[ "$output" == *"invalid ep_id"* ]]
}

@test "concat: missing videos dir → exit 1" {
  run bash "$SCRIPT" "test-ep"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not found"* ]]
}

@test "concat: empty videos dir (no shot files) → exit 1" {
  mkdir -p "outputs/test-ep/videos"
  run bash "$SCRIPT" "test-ep"
  [ "$status" -eq 1 ]
  [[ "$output" == *"No shot files found"* ]]
}

@test "concat: ffmpeg not found → exit 1" {
  # 临时 PATH 不含 ffmpeg（也排除 stub）
  run env PATH="/usr/bin:/bin" bash "$SCRIPT" "test-ep"
  [ "$status" -ne 0 ]
  [[ "$output" == *"ffmpeg"* ]]
}

# ── silent audio padding (has_audio=0) ──────────────────────────────────────

@test "concat: no-audio shot triggers anullsrc padding" {
  mkdir -p "outputs/test-ep/videos"
  echo "fake-video" > "outputs/test-ep/videos/shot-01.mp4"

  # ffprobe stub that reports NO audio stream
  cat > "${STUB_BIN}/ffprobe" << 'PROBSTUB'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == "-select_streams" ]]; then SELECT=next; continue; fi
  if [[ "${SELECT:-}" == "next" && "$arg" == "a" ]]; then
    exit 0  # empty output = no audio
  fi
  if [[ "$arg" == "-show_entries" ]]; then SHOW=next; continue; fi
  if [[ "${SHOW:-}" == "next" && "$arg" == "format=duration" ]]; then
    echo "8.0"; exit 0
  fi
done
PROBSTUB
  chmod +x "${STUB_BIN}/ffprobe"

  # ffmpeg stub that logs calls so we can verify anullsrc was used
  cat > "${STUB_BIN}/ffmpeg" << 'FFSTUB'
#!/usr/bin/env bash
echo "$@" >> /tmp/bats-ffmpeg-calls.txt
# Create output files
for arg in "$@"; do
  if [[ "$arg" == *.mp4 ]] && [[ "$arg" != *"shot-"*.mp4 || "$arg" == *"/normalized/"* ]]; then
    echo "stub" > "$arg"
  fi
done
exit 0
FFSTUB
  chmod +x "${STUB_BIN}/ffmpeg"
  rm -f /tmp/bats-ffmpeg-calls.txt

  run bash "$SCRIPT" "test-ep"
  # The script should have called ffmpeg with anullsrc for the no-audio shot
  [ -f /tmp/bats-ffmpeg-calls.txt ]
  run grep "anullsrc" /tmp/bats-ffmpeg-calls.txt
  [ "$status" -eq 0 ]
  rm -f /tmp/bats-ffmpeg-calls.txt
}

# ── normal concat flow ──────────────────────────────────────────────────────

@test "concat: normal flow with audio shots succeeds" {
  mkdir -p "outputs/test-ep/videos"
  echo "fake-video-1" > "outputs/test-ep/videos/shot-01.mp4"
  echo "fake-video-2" > "outputs/test-ep/videos/shot-02.mp4"

  # ffprobe: reports audio present + duration
  cat > "${STUB_BIN}/ffprobe" << 'PROBSTUB'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == "-select_streams" ]]; then SELECT=next; continue; fi
  if [[ "${SELECT:-}" == "next" && "$arg" == "a" ]]; then
    echo "codec_name=aac"; exit 0
  fi
  if [[ "$arg" == "-show_entries" ]]; then SHOW=next; continue; fi
  if [[ "${SHOW:-}" == "next" && "$arg" == "format=duration" ]]; then
    echo "16.0"; exit 0
  fi
done
echo "codec_name=aac"
PROBSTUB
  chmod +x "${STUB_BIN}/ffprobe"

  # ffmpeg: create output files
  cat > "${STUB_BIN}/ffmpeg" << 'FFSTUB'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == *.mp4 && ! -f "$arg" ]]; then
    echo "stub" > "$arg"
  fi
done
exit 0
FFSTUB
  chmod +x "${STUB_BIN}/ffmpeg"

  run bash "$SCRIPT" "test-ep"
  [ "$status" -eq 0 ]
  [[ "$output" == *"完成"* ]]
  [[ "$output" == *"保留"* ]]
}

@test "concat: project mode writes human-facing deliverables layout" {
  mkdir -p "projects/demo/outputs/ep01/videos"
  echo "fake-video-1" > "projects/demo/outputs/ep01/videos/shot-01.mp4"
  echo "fake-video-2" > "projects/demo/outputs/ep01/videos/shot-02.mp4"

  cat > "${STUB_BIN}/ffprobe" << 'PROBSTUB'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == "-select_streams" ]]; then SELECT=next; continue; fi
  if [[ "${SELECT:-}" == "next" && "$arg" == "a" ]]; then
    echo "codec_name=aac"; exit 0
  fi
  if [[ "$arg" == "-show_entries" ]]; then SHOW=next; continue; fi
  if [[ "${SHOW:-}" == "next" && "$arg" == "format=duration" ]]; then
    echo "16.0"; exit 0
  fi
done
echo "codec_name=aac"
PROBSTUB
  chmod +x "${STUB_BIN}/ffprobe"

  cat > "${STUB_BIN}/ffmpeg" << 'FFSTUB'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == *.mp4 && ! -f "$arg" ]]; then
    mkdir -p "$(dirname "$arg")"
    echo "stub" > "$arg"
  fi
done
exit 0
FFSTUB
  chmod +x "${STUB_BIN}/ffmpeg"

  run bash "$SCRIPT" --project demo ep01
  [ "$status" -eq 0 ]
  [ -f "projects/demo/outputs/ep01/deliverables/final.mp4" ]
  [ -f "projects/demo/outputs/ep01/deliverables/shots/shot-01.mp4" ]
  [ -f "projects/demo/outputs/ep01/deliverables/shots/shot-02.mp4" ]
  [ -f "projects/demo/outputs/ep01/deliverables/manifest.json" ]
}
