#!/bin/bash
# scripts/nanobanana-caller.sh
# Nanobanana API 调用脚本（通过 Tuzi gpt-image-2 default 分组）

set -euo pipefail

TUZI_API_KEY="${TUZI_API_KEY:-}"
NANOBANANA_API_KEY="${NANOBANANA_API_KEY:-$TUZI_API_KEY}"
CONFIG_FILE="config/nanobanana/nanobanana-config.yaml"

# 读取配置
if [[ -f "$CONFIG_FILE" ]]; then
    MODEL=$(yq eval '.api.model' "$CONFIG_FILE")
    BASE_URL=$(yq eval '.api.base_url' "$CONFIG_FILE")
else
    MODEL="gpt-image-2"
    BASE_URL="https://api.tu-zi.com/v1"
fi

API_URL="${BASE_URL}/images/generations"

# 检查 API Key
if [[ -z "$NANOBANANA_API_KEY" ]]; then
    echo "错误: 未设置 TUZI_API_KEY 或 NANOBANANA_API_KEY" >&2
    exit 1
fi

# 映射 image_size 到 quality
map_quality() {
    local image_size="$1"
    case "$image_size" in
        2K|2k) echo "high" ;;
        1K|1k) echo "medium" ;;
        *) echo "auto" ;;
    esac
}

# 生成图像（文生图）
generate_image() {
    local prompt="$1"
    local aspect_ratio="${2:-1:1}"
    local image_size="${3:-2K}"
    local output_path="$4"

    echo "生成图像: $output_path" >&2
    echo "  提示词: ${prompt:0:100}..." >&2
    echo "  宽高比: $aspect_ratio" >&2
    echo "  分辨率: $image_size" >&2

    local quality
    quality=$(map_quality "$image_size")

    local payload
    payload=$(jq -cn \
        --arg model "$MODEL" \
        --arg prompt "$prompt" \
        --arg size "$aspect_ratio" \
        --arg quality "$quality" \
        '{
            model: $model,
            prompt: $prompt,
            n: 1,
            size: $size,
            quality: $quality,
            response_format: "url"
        }')

    local response
    response=$(curl -sS --fail-with-body \
        --connect-timeout 10 \
        --max-time 120 \
        -X POST "$API_URL" \
        -H "Authorization: Bearer ${NANOBANANA_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$payload")

    # 检查错误
    if echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        echo "错误: $(echo "$response" | jq -r '.error.message // .error')" >&2
        return 1
    fi

    # 提取 URL 并下载图片
    local image_url
    image_url=$(echo "$response" | jq -r '.data[0].url // empty')
    if [[ -z "$image_url" ]]; then
        echo "错误: 响应中未找到图片 URL" >&2
        echo "响应: $response" >&2
        return 1
    fi

    curl -sS --max-time 60 -o "$output_path" "$image_url"

    if [[ -f "$output_path" && -s "$output_path" ]]; then
        local size
        size=$(du -h "$output_path" | cut -f1)
        echo "✓ 图像已保存: $output_path ($size)" >&2
        return 0
    else
        echo "错误: 图像下载失败" >&2
        rm -f "$output_path"
        return 1
    fi
}

# 图生图
generate_image_from_ref() {
    local prompt="$1"
    local ref_image="$2"
    local aspect_ratio="${3:-1:1}"
    local image_size="${4:-2K}"
    local output_path="$5"

    echo "图生图: $output_path" >&2
    echo "  提示词: ${prompt:0:100}..." >&2
    echo "  参考图: $ref_image" >&2

    local quality
    quality=$(map_quality "$image_size")

    local payload
    payload=$(jq -cn \
        --arg model "$MODEL" \
        --arg prompt "$prompt" \
        --arg image "$ref_image" \
        --arg size "$aspect_ratio" \
        --arg quality "$quality" \
        '{
            model: $model,
            prompt: $prompt,
            image: $image,
            n: 1,
            size: $size,
            quality: $quality,
            response_format: "url"
        }')

    local response
    response=$(curl -sS --fail-with-body \
        --connect-timeout 10 \
        --max-time 120 \
        -X POST "$API_URL" \
        -H "Authorization: Bearer ${NANOBANANA_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        echo "错误: $(echo "$response" | jq -r '.error.message // .error')" >&2
        return 1
    fi

    local image_url
    image_url=$(echo "$response" | jq -r '.data[0].url // empty')
    if [[ -z "$image_url" ]]; then
        echo "错误: 响应中未找到图片 URL" >&2
        return 1
    fi

    curl -sS --max-time 60 -o "$output_path" "$image_url"

    if [[ -f "$output_path" && -s "$output_path" ]]; then
        local size
        size=$(du -h "$output_path" | cut -f1)
        echo "✓ 图像已保存: $output_path ($size)" >&2
        return 0
    else
        echo "错误: 图像下载失败" >&2
        rm -f "$output_path"
        return 1
    fi
}

# 生成角色定妆包
generate_character_pack() {
    local character_name="$1"
    local variant="$2"
    local appearance="$3"
    local output_dir="assets/packs/characters"

    mkdir -p "$output_dir"

    # 正面
    local prompt_front="角色设计图，${character_name}，${appearance}，正面视图，面向镜头，白色背景，角色设计稿风格，全身像，高清细节，无水印，无文字，纯净背景"
    generate_image "$prompt_front" "1:1" "2K" "${output_dir}/${character_name}-${variant}-front.png"

    # 侧面
    local prompt_side="角色设计图，${character_name}，${appearance}，侧面视图，90度侧身，白色背景，角色设计稿风格，全身像，高清细节，无水印，无文字，纯净背景"
    generate_image "$prompt_side" "1:1" "2K" "${output_dir}/${character_name}-${variant}-side.png"

    # 背面
    local prompt_back="角色设计图，${character_name}，${appearance}，背面视图，背对镜头，白色背景，角色设计稿风格，全身像，高清细节，无水印，无文字，纯净背景"
    generate_image "$prompt_back" "1:1" "2K" "${output_dir}/${character_name}-${variant}-back.png"

    echo "✓ 角色定妆包生成完成: ${character_name}-${variant}" >&2
}

# 生成场景 styleframe
generate_scene_styleframe() {
    local scene_name="$1"
    local time_of_day="$2"
    local scene_description="$3"
    local lighting="$4"
    local output_dir="assets/packs/scenes"

    mkdir -p "$output_dir"

    local time_desc=""
    case "$time_of_day" in
        day) time_desc="白天，明亮自然光" ;;
        night) time_desc="夜晚，${lighting}" ;;
        dusk) time_desc="黄昏，暖色调夕阳" ;;
        dawn) time_desc="清晨，柔和晨光" ;;
    esac

    local prompt="场景设计图，${scene_name}，${scene_description}，${time_desc}，电影级场景概念图，高清细节，无人物，无水印"
    generate_image "$prompt" "16:9" "2K" "${output_dir}/${scene_name}-${time_of_day}-styleframe.png"

    echo "✓ 场景 styleframe 生成完成: ${scene_name}-${time_of_day}" >&2
}

# 生成道具包
generate_prop_pack() {
    local prop_name="$1"
    local description="$2"
    local condition="$3"
    local output_dir="assets/packs/props"

    mkdir -p "$output_dir"

    local condition_desc=""
    case "$condition" in
        intact) condition_desc="完好无损" ;;
        damaged) condition_desc="破损" ;;
        destroyed) condition_desc="毁坏" ;;
    esac

    local prompt="道具设计图，${prop_name}，${description}，${condition_desc}，白色背景，产品设计稿风格，高清细节，无水印"
    generate_image "$prompt" "1:1" "1K" "${output_dir}/${prop_name}-${condition}.png"

    echo "✓ 道具包生成完成: ${prop_name}-${condition}" >&2
}

# 主函数
main() {
    local command="${1:-}"

    case "$command" in
        generate)
            generate_image "$2" "$3" "$4" "$5"
            ;;
        image-from-ref)
            generate_image_from_ref "$2" "$3" "$4" "$5" "$6"
            ;;
        character-pack)
            generate_character_pack "$2" "$3" "$4"
            ;;
        scene-styleframe)
            generate_scene_styleframe "$2" "$3" "$4" "$5"
            ;;
        prop-pack)
            generate_prop_pack "$2" "$3" "$4"
            ;;
        *)
            echo "用法: $0 <command> [args...]"
            echo ""
            echo "命令:"
            echo "  generate <prompt> <aspect_ratio> <image_size> <output_path>"
            echo "  image-from-ref <prompt> <ref_image_url> <aspect_ratio> <image_size> <output_path>"
            echo "  character-pack <name> <variant> <appearance>"
            echo "  scene-styleframe <name> <time_of_day> <description> <lighting>"
            echo "  prop-pack <name> <description> <condition>"
            exit 1
            ;;
    esac
}

main "$@"
