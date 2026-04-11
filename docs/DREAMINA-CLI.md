# Dreamina CLI（即梦官方 CLI）

即梦官方 AIGC CLI 工具，支持全部生成能力，作为视频/图像生成后端。

## 安装

```bash
curl -fsSL https://jimeng.jianying.com/cli | bash
```

## 登录

```bash
dreamina login                    # 浏览器授权
dreamina login --headless         # 终端 QR 码（适合远程/agent 环境）
dreamina user_credit              # 验证登录状态 + 查看余额
```

## 切换后端

修改 `config/platforms/seedance-v2.yaml`：
```yaml
generation_backend: "dreamina"  # 从 "api" 改为 "dreamina"
```

## 生成能力

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `text2video` | 文生视频 | `--prompt`, `--duration`(4-15), `--ratio`, `--model_version`(seedance2.0/seedance2.0fast) |
| `image2video` | 图生视频（单图） | `--image`(本地路径), `--prompt`, `--duration`, `--model_version` |
| `multimodal2video` | 多模态旗舰视频（推荐） | `--image`×9, `--video`×3, `--audio`×3, `--prompt`, Seedance 2.0 |
| `multiframe2video` | 多帧连贯视频故事 | `--images`(2-20张), `--transition-prompt`, `--transition-duration` |
| `frames2video` | 首尾帧视频 | `--first`, `--last`, `--prompt`, `--duration` |
| `text2image` | 文生图 | `--prompt`, `--ratio`, `--resolution_type`(2k/4k), `--model_version`(3.0-5.0) |
| `image2image` | 图生图 | `--images`, `--prompt`, `--resolution_type` |
| `image_upscale` | 图片超分 | `--image`, `--resolution_type`(2k/4k/8k) |

## 管理命令

```bash
dreamina user_credit                              # 查看余额
dreamina query_result --submit_id=<id>            # 查询异步任务
dreamina query_result --submit_id=<id> --download_dir=./out  # 查询并下载
dreamina list_task                                # 查看任务列表
dreamina list_task --gen_status=success           # 按状态筛选
dreamina relogin                                  # 重新登录
dreamina logout                                   # 清除登录
dreamina import_login_response --file <json>      # 导入登录凭证
```

## 通过 api-caller.sh 调用

```bash
./scripts/api-caller.sh dreamina submit <payload.json>   # 提交生成任务
./scripts/api-caller.sh dreamina query <submit_id>       # 查询任务结果
./scripts/api-caller.sh dreamina download <submit_id> <dir>  # 下载结果
./scripts/api-caller.sh dreamina credit                  # 查询余额
./scripts/api-caller.sh dreamina list                    # 查看任务列表
./scripts/api-caller.sh dreamina login-check             # 检查登录状态
```

## 注意事项

- 所有生成命令消耗 credit，提交前确认余额
- `multimodal2video` 是最强视频模式，支持 Seedance 2.0 + 混合输入
- 参考图使用本地文件路径（非 URL）
- 部分模型首次使用需在即梦 Web 端完成授权确认（`AigcComplianceConfirmationRequired`）
- `--poll=N` 可让 CLI 等待 N 秒后返回结果，超时则返回 `submit_id` 供后续查询
