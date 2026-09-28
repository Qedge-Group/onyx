# 14B 本地模型 RAG 优化版部署指南

本文档适用于 `Qedge-Group/onyx` 仓库的 `codex/rag-quality-14b` 分支。

该分支基于 Onyx `v4.6.3`。它改进了小型本地模型的检索结果筛选和上下文预算。

## 1. 变更范围

该分支保留 Onyx 原有的混合检索、RRF、Reranker 和相邻片段扩展。

主要变更如下：

- 普通问题至少保留 3 个候选片段。
- 高召回问题至少保留 10 个候选片段。
- 补充片段时优先选择不同文档。
- 根据模型上下文窗口限制最终片段数量。
- 增加 `rag_section_selection` 和 `rag_search_pipeline` 日志。

这些变更只影响聊天和搜索 API。它们不修改数据库结构和索引格式。

## 2. 版本和资源要求

建议使用以下版本：

| 组件 | 建议值 |
| --- | --- |
| Onyx 基线 | `v4.6.3` |
| 自定义分支 | `codex/rag-quality-14b` |
| Ollama 模型 | `qwen3-custom:14b-20k` |
| 模型上下文 | `20480` tokens |
| GPU 显存 | 24 GB 或更多 |
| Docker | 24 或更新版本 |
| Docker Compose | Compose V2 |

不要让其他 Onyx 服务长期使用 `latest`。本分支基于 `v4.6.3`。

升级 Onyx 基线前，先将该分支变基或合并到新版本。然后重新执行测试。

## 3. 准备 GitHub SSH 访问

服务器必须能读取 `Qedge-Group/onyx` 仓库。

测试 SSH：

```bash
ssh -T git@github.com
```

如果服务器使用 `github-onyx` SSH 别名，则执行：

```bash
ssh -T git@github-onyx
```

成功信息中应显示有仓库权限的 GitHub 用户名。

## 4. 全新部署

### 4.1 克隆指定分支

使用标准 GitHub SSH 地址：

```bash
sudo mkdir -p /opt/qedge/docker
cd /opt/qedge/docker

git clone \
  --branch codex/rag-quality-14b \
  --single-branch \
  git@github.com:Qedge-Group/onyx.git \
  onyx-rag-quality-14b

cd /opt/qedge/docker/onyx-rag-quality-14b
```

使用 `github-onyx` 别名时，将仓库地址改成：

```text
git@github-onyx:Qedge-Group/onyx.git
```

确认版本：

```bash
git status --short --branch
git log -3 --oneline
```

### 4.2 准备 Onyx 环境文件

进入 Compose 目录：

```bash
cd deployment/docker_compose
cp env.prod.template .env
```

编辑 `.env`：

```bash
vi .env
```

至少设置以下内容：

```dotenv
IMAGE_TAG=v4.6.3
WEB_DOMAIN=https://你的-Onyx-域名
POSTGRES_PASSWORD=请使用强密码
DB_READONLY_PASSWORD=请使用另一个强密码
OPENSEARCH_ADMIN_PASSWORD=请使用强密码
MINIO_ROOT_USER=请使用非默认用户名
MINIO_ROOT_PASSWORD=请使用强密码
S3_AWS_ACCESS_KEY_ID=使用与MINIO_ROOT_USER相同的值
S3_AWS_SECRET_ACCESS_KEY=使用与MINIO_ROOT_PASSWORD相同的值
```

不要把 `.env`、密码或 API 密钥提交到 Git。

### 4.3 构建自定义后端镜像

回到仓库根目录：

```bash
cd /opt/qedge/docker/onyx-rag-quality-14b
```

使用当前提交生成不可变镜像标签：

```bash
RAG_COMMIT="$(git rev-parse --short HEAD)"
RAG_IMAGE="onyx-backend:rag-quality-14b-${RAG_COMMIT}"

docker build \
  --target runtime \
  -f backend/Dockerfile \
  -t "${RAG_IMAGE}" \
  --build-arg "ONYX_VERSION=v4.6.3-rag-${RAG_COMMIT}" \
  backend
```

确认镜像存在：

```bash
docker image inspect "${RAG_IMAGE}" --format '{{.Id}} {{.Created}}'
```

### 4.4 创建 Compose 覆盖文件

在 `deployment/docker_compose` 中创建 `docker-compose.rag-quality.yml`：

```yaml
services:
  api_server:
    image: ${ONYX_RAG_BACKEND_IMAGE}
    environment:
      SEARCH_CONTEXT_TOKEN_RESERVE: "4096"
      SEARCH_CHUNK_TOKEN_OVERHEAD: "128"
      SEARCH_MIN_SELECTED_SECTIONS: "3"
      SEARCH_HIGH_RECALL_SELECTED_SECTIONS: "10"
```

将镜像名称写入 `.env`。使用前面构建的真实标签：

```dotenv
ONYX_RAG_BACKEND_IMAGE=onyx-backend:rag-quality-14b-9f7baf2dd1
```

不要直接复制示例提交号。执行以下命令可取得当前提交号：

```bash
git rev-parse --short HEAD
```

### 4.5 验证 Compose 配置

无自定义 `docker-compose.override.yml` 时执行：

```bash
cd deployment/docker_compose

docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.rag-quality.yml \
  config --quiet
```

已有 `docker-compose.override.yml` 时执行：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.override.yml \
  -f docker-compose.rag-quality.yml \
  config --quiet
```

该命令没有输出时，配置有效。

### 4.6 启动服务

全新部署且没有自定义覆盖文件：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.rag-quality.yml \
  up -d
```

已有自定义覆盖文件：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.override.yml \
  -f docker-compose.rag-quality.yml \
  up -d
```

## 5. 升级现有 Onyx 环境

本节适用于已经运行的 Onyx。

### 5.1 记录当前状态

```bash
docker ps --format \
  'table {{.Names}}\t{{.Image}}\t{{.CreatedAt}}\t{{.Status}}'

docker inspect onyx-api_server-1 --format \
  'image={{.Config.Image}} id={{.Image}} created={{.Created}} started={{.State.StartedAt}}'
```

记录当前 Compose 文件：

```bash
docker inspect onyx-api_server-1 --format \
  '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
```

### 5.2 保存旧镜像

```bash
OLD_IMAGE_ID="$(docker inspect onyx-api_server-1 --format '{{.Image}}')"
docker tag "${OLD_IMAGE_ID}" onyx-backend:pre-rag-quality
```

确认回滚镜像：

```bash
docker image inspect onyx-backend:pre-rag-quality --format '{{.Id}}'
```

### 5.3 获取和构建新分支

可以使用独立克隆，也可以使用 Git worktree。

独立克隆示例：

```bash
cd /opt/qedge/docker

git clone \
  --branch codex/rag-quality-14b \
  --single-branch \
  git@github.com:Qedge-Group/onyx.git \
  onyx-rag-quality-14b

cd onyx-rag-quality-14b
```

构建镜像：

```bash
RAG_COMMIT="$(git rev-parse --short HEAD)"
RAG_IMAGE="onyx-backend:rag-quality-14b-${RAG_COMMIT}"

docker build \
  --target runtime \
  -f backend/Dockerfile \
  -t "${RAG_IMAGE}" \
  --build-arg "ONYX_VERSION=v4.6.3-rag-${RAG_COMMIT}" \
  backend
```

### 5.4 只切换 API 服务

把 `docker-compose.rag-quality.yml` 放在稳定的运行目录中。

示例路径：

```text
/opt/qedge/docker/onyx/runtime/docker-compose.rag-quality.yml
```

覆盖文件内容：

```yaml
services:
  api_server:
    image: ${ONYX_RAG_BACKEND_IMAGE}
    environment:
      SEARCH_CONTEXT_TOKEN_RESERVE: "4096"
      SEARCH_CHUNK_TOKEN_OVERHEAD: "128"
      SEARCH_MIN_SELECTED_SECTIONS: "3"
      SEARCH_HIGH_RECALL_SELECTED_SECTIONS: "10"
```

在原 Compose 目录的 `.env` 中设置镜像：

```dotenv
ONYX_RAG_BACKEND_IMAGE=onyx-backend:rag-quality-14b-当前提交号
```

先检查合并结果：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.override.yml \
  -f /opt/qedge/docker/onyx/runtime/docker-compose.rag-quality.yml \
  config --quiet
```

然后只重建 API 容器：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.override.yml \
  -f /opt/qedge/docker/onyx/runtime/docker-compose.rag-quality.yml \
  up -d --no-deps --force-recreate api_server
```

这一步不会重启 PostgreSQL、OpenSearch、Redis、后台任务或 Ollama。

`RestartCount=0` 是正常结果。Compose 创建了新容器，不是在旧容器中执行重启。

## 6. 在独立服务器部署 Ollama 14B 模型

本节以 Ubuntu 24.04、NVIDIA GPU 和 systemd 为例。

目标模型名称为：

```text
onyx-qwen3-14b-20k:latest
```

Ollama 官方 Linux 安装说明：<https://ollama.com/download/linux>

Ollama 官方服务配置说明：<https://docs.ollama.com/faq>

### 6.1 检查服务器资源

登录 Ollama 服务器：

```bash
ssh root@OLLAMA_SERVER_IP
```

检查操作系统：

```bash
cat /etc/os-release
```

检查 GPU 和驱动：

```bash
nvidia-smi
```

检查内存和磁盘：

```bash
free -h
df -h /
```

建议至少保留 20 GB 磁盘空间。模型本身约占 9.3 GB。

如果 `nvidia-smi` 失败，先安装云厂商推荐的 NVIDIA 驱动。

安装驱动后重启服务器。确认 `nvidia-smi` 正常后再安装 Ollama。

### 6.2 安装 Ollama

执行官方 Linux 安装脚本：

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

确认命令和版本：

```bash
command -v ollama
ollama --version
```

确认 systemd 服务：

```bash
systemctl status ollama --no-pager
systemctl is-enabled ollama
systemctl is-active ollama
```

如果服务没有启动，执行：

```bash
systemctl enable --now ollama
```

检查本机 API：

```bash
curl -fsS http://127.0.0.1:11434/api/version
```

Linux 默认模型目录为：

```text
/usr/share/ollama/.ollama/models
```

### 6.3 配置 24GB GPU 运行参数

默认情况下，Ollama 只监听 `127.0.0.1:11434`。

Onyx 在另一台服务器时，需要监听内网地址。

使用 systemd 覆盖文件，不要直接修改安装程序创建的服务文件：

```bash
systemctl edit ollama.service
```

加入以下内容：

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=15m"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
```

这些设置有以下作用：

- 一次只加载一个模型。
- 每个模型一次只处理一个请求。
- 模型空闲 15 分钟后可以释放。
- Flash Attention 可降低长上下文的显存需求。

保存文件后重新加载服务：

```bash
systemctl daemon-reload
systemctl restart ollama
```

确认环境变量已经生效：

```bash
systemctl show ollama -p Environment --no-pager
ss -lntp | grep ':11434'
```

24GB GPU 应先使用默认的 `f16` KV Cache。

如果 20K 上下文仍然显存不足，可以加入以下可选设置：

```ini
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
```

`q8_0` KV Cache 的显存约为 `f16` 的一半。它可能带来很小的精度变化。

修改后执行：

```bash
systemctl daemon-reload
systemctl restart ollama
```

### 6.4 限制网络访问

Ollama API 默认没有业务层身份验证。

不要允许整个公网访问 TCP `11434`。

优先使用以下任一方式：

1. 让 Onyx 和 Ollama 使用同一私有网络。
2. 使用 WireGuard 或 Tailscale。
3. 使用云安全组，只允许 Onyx 服务器访问 `11434`。
4. 使用主机防火墙，只允许 Onyx 的固定来源 IP。

使用 UFW 时，先保证 SSH 端口不会被阻止。

示例规则如下：

```bash
ufw allow OpenSSH
ufw allow from ONYX_SERVER_SOURCE_IP to any port 11434 proto tcp
ufw deny 11434/tcp
ufw status numbered
```

不要直接复制占位 IP。应填写 Ollama 实际看到的 Onyx 来源 IP。

如果使用云安全组，应同时删除面向 `0.0.0.0/0` 的 `11434` 入站规则。

### 6.5 下载 Qwen3 14B 基础模型

拉取基础模型：

```bash
ollama pull qwen3:14b
```

检查模型：

```bash
ollama list
ollama show qwen3:14b --parameters
```

基础模型约占 9.3 GB。实际大小可能随上游模型版本变化。

### 6.6 创建 20K RAG 模型

创建配置目录：

```bash
install -d -m 0755 /opt/ollama-models/qwen3-14b-20k
cd /opt/ollama-models/qwen3-14b-20k
```

创建 `Modelfile`：

```text
FROM qwen3:14b

SYSTEM """
你是一个基于知识库检索结果回答问题的助手。
只根据提供的知识库内容回答。
资料不足时明确说明，不得编造。
回答应保留来源引用。
除非任务确实需要，不要展示冗长的推理过程。
"""

PARAMETER num_ctx 20480
PARAMETER num_predict 1024
PARAMETER temperature 0.1
PARAMETER top_k 20
PARAMETER top_p 0.8
PARAMETER repeat_penalty 1.05
```

创建自定义模型：

```bash
ollama create onyx-qwen3-14b-20k:latest -f Modelfile
```

确认模型和参数：

```bash
ollama list
ollama show onyx-qwen3-14b-20k:latest --parameters
```

预期参数至少包含：

```text
temperature       0.1
top_k             20
top_p             0.8
num_ctx           20480
num_predict       1024
repeat_penalty    1.05
```

### 6.7 测试模型生成

先执行命令行测试：

```bash
ollama run onyx-qwen3-14b-20k:latest \
  '请用一句话回答：知识库检索测试成功。'
```

再执行 API 测试：

```bash
curl -fsS http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "onyx-qwen3-14b-20k:latest",
    "messages": [
      {"role": "user", "content": "请回答：API 测试成功"}
    ],
    "stream": false
  }'
```

测试后查看加载状态：

```bash
ollama ps
nvidia-smi
```

`ollama ps` 的 `PROCESSOR` 应显示 `100% GPU`。

如果显示 CPU/GPU 混合，则模型或上下文可能超过可用显存。

### 6.8 从 Onyx 服务器测试网络

登录 Onyx 服务器。使用 Ollama 的私有地址执行：

```bash
curl -fsS http://OLLAMA_PRIVATE_IP:11434/api/version
```

测试模型列表：

```bash
curl -fsS http://OLLAMA_PRIVATE_IP:11434/api/tags
```

测试一次生成：

```bash
curl -fsS http://OLLAMA_PRIVATE_IP:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "onyx-qwen3-14b-20k:latest",
    "messages": [
      {"role": "user", "content": "请回答：Onyx 到 Ollama 网络正常"}
    ],
    "stream": false
  }'
```

如果连接失败，检查以下项目：

```bash
systemctl status ollama --no-pager
ss -lntp | grep ':11434'
journalctl -u ollama --since '10 minutes ago' --no-pager
```

同时检查云安全组、主机防火墙和私有网络路由。

### 6.9 在 Onyx 中添加模型

在 Onyx 管理界面打开 LLM Provider 设置。

添加 Ollama Provider，并填写以下值：

| 项目 | 值 |
| --- | --- |
| Provider | Ollama |
| Base URL | `http://OLLAMA_PRIVATE_IP:11434` |
| Model name | `onyx-qwen3-14b-20k:latest` |
| Max input tokens | `20480` |

Onyx 的 Max input tokens 必须与 Ollama 的 `num_ctx` 一致。

不要为 20K 模型填写 `262144`。过大的值会增加 KV Cache 和显存占用。

将该模型设为默认聊天模型。保存后新建会话执行测试。

### 6.10 预热、卸载和升级

发送空请求可以预热模型：

```bash
curl -fsS http://127.0.0.1:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "onyx-qwen3-14b-20k:latest",
    "keep_alive": "15m"
  }'
```

手动卸载模型并释放显存：

```bash
ollama stop onyx-qwen3-14b-20k:latest
```

升级 Ollama 前先记录版本：

```bash
ollama --version
```

Linux 升级命令与安装命令相同：

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

不要直接在生产高峰期升级。升级后应重新执行 API、显存和 RAG 测试。

### 6.11 Ollama 常见问题

#### 模型只使用 CPU

检查 NVIDIA 驱动：

```bash
nvidia-smi
journalctl -u ollama --since '10 minutes ago' --no-pager
ollama ps
```

#### 24GB GPU 显存不足

按以下顺序处理：

1. 确认 `OLLAMA_MAX_LOADED_MODELS=1`。
2. 确认 `OLLAMA_NUM_PARALLEL=1`。
3. 停止其他已加载模型。
4. 确认上下文为 `20480`，不是 `262144`。
5. 启用 `OLLAMA_FLASH_ATTENTION=1`。
6. 最后尝试 `OLLAMA_KV_CACHE_TYPE=q8_0`。

#### 首次回答很慢

首次请求需要加载约 9.3 GB 模型权重。

使用预热请求，并设置合理的 `OLLAMA_KEEP_ALIVE`。

#### Onyx 报超时

先在 Ollama 本机测试相同模型。

然后检查 Onyx 到 Ollama 的延迟和防火墙。

确认没有其他模型占用 GPU。检查 `ollama ps` 和 `nvidia-smi`。

## 7. RAG 参数

该分支支持以下环境变量：

| 变量 | 默认值 | 说明 |
| --- | ---: | --- |
| `SEARCH_CONTEXT_TOKEN_RESERVE` | `4096` | 为提示词、历史和回答保留的 tokens |
| `SEARCH_CHUNK_TOKEN_OVERHEAD` | `128` | 每个片段的标题和结构开销 |
| `SEARCH_MIN_SELECTED_SECTIONS` | `3` | 普通问题的最低片段数 |
| `SEARCH_HIGH_RECALL_SELECTED_SECTIONS` | `10` | 高召回问题的最低片段数 |

推荐先使用默认值。

对于 8K 模型，默认预算通常允许约 6 个片段。

对于 20K 模型，默认预算通常允许最多 25 个片段。

增加片段数可能降低速度和精度。每次只调整一个参数。

## 8. 部署验证

### 8.1 检查容器和镜像

```bash
docker ps --format \
  'table {{.Names}}\t{{.Image}}\t{{.CreatedAt}}\t{{.Status}}' \
  | grep -E 'onyx-api_server|onyx-background'
```

预期结果：

- `onyx-api_server-1` 使用自定义 RAG 镜像。
- `onyx-api_server-1` 状态为 `healthy`。
- `onyx-background-1` 可以继续使用官方后端镜像。

查看精确状态：

```bash
docker inspect onyx-api_server-1 --format \
  'image={{.Config.Image}} id={{.Image}} health={{.State.Health.Status}} restarts={{.RestartCount}}'
```

### 8.2 检查健康接口

```bash
docker exec onyx-api_server-1 python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/health').read().decode())"
```

### 8.3 检查启动日志

```bash
docker logs --since 10m onyx-api_server-1 2>&1 \
  | grep -E 'Application startup complete|ERROR|Traceback|CRITICAL'
```

启动日志应包含：

```text
Application startup complete.
```

### 8.4 执行 RAG 测试

至少测试以下三类问题：

1. 单一事实问题。
2. 多文档比较问题。
3. 完整列举或汇总问题。

高召回测试示例：

```text
请总结知识库中已收录的客户案例，并提供对应引用。
```

测试后检查结构化日志：

```bash
docker logs --since 10m onyx-api_server-1 2>&1 \
  | grep -E 'event=rag_section_selection|event=rag_search_pipeline'
```

重点检查以下字段：

- `high_recall`
- `retrieved_chunks`
- `selection_candidates`
- `selected`
- `llm_chunk_limit`

`rag_section_selection` 日志还包含以下字段：

- `candidates`
- `llm_selected`
- `final_selected`
- `minimum`

高召回问题应显示 `high_recall=True`。

## 9. 回滚

如果新 API 容器不健康，先把覆盖文件中的镜像改成：

```yaml
services:
  api_server:
    image: onyx-backend:pre-rag-quality
```

重新检查配置：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.override.yml \
  -f /opt/qedge/docker/onyx/runtime/docker-compose.rag-quality.yml \
  config --quiet
```

执行回滚：

```bash
docker compose \
  -f docker-compose.prod-no-letsencrypt.yml \
  -f docker-compose.override.yml \
  -f /opt/qedge/docker/onyx/runtime/docker-compose.rag-quality.yml \
  up -d --no-deps --force-recreate api_server
```

确认状态：

```bash
docker inspect onyx-api_server-1 --format \
  'image={{.Config.Image}} health={{.State.Health.Status}}'
```

该分支没有数据库迁移。回滚不需要恢复数据库或重建索引。

## 10. 更新该分支

拉取新提交：

```bash
cd /opt/qedge/docker/onyx-rag-quality-14b
git checkout codex/rag-quality-14b
git pull --ff-only
```

为新提交构建新镜像：

```bash
RAG_COMMIT="$(git rev-parse --short HEAD)"
RAG_IMAGE="onyx-backend:rag-quality-14b-${RAG_COMMIT}"

docker build \
  --target runtime \
  -f backend/Dockerfile \
  -t "${RAG_IMAGE}" \
  --build-arg "ONYX_VERSION=v4.6.3-rag-${RAG_COMMIT}" \
  backend
```

更新 `.env` 中的 `ONYX_RAG_BACKEND_IMAGE`。然后重新创建 API 容器。

不要覆盖旧的不可变镜像标签。保留最近一个健康版本用于回滚。

## 11. 升级 Onyx 基线

该分支不能永久停留在 `v4.6.3`。

升级步骤如下：

1. 从 Onyx 官方仓库获取新的稳定版本。
2. 创建新的升级分支。
3. 合并或移植本分支的两个提交。
4. 解决搜索管线的代码冲突。
5. 运行相关单元测试。
6. 构建带新提交号的镜像。
7. 在测试环境执行 RAG 对比测试。
8. 更新 `IMAGE_TAG` 和自定义后端镜像。
9. 切换生产 API 容器。

当前 RAG 变更提交：

```text
1a5b95b0bd Improve RAG coverage for small local models
9f7baf2dd1 Detect broad knowledge-base summary queries
```

升级时优先移植这两个提交。不要复制整个旧工作目录。

## 12. 常见问题

### API 容器显示 RestartCount 为 0

这是正常结果。Compose 删除了旧容器并创建了新容器。

使用 `CreatedAt`、镜像名称和镜像 ID 判断是否切换成功。

### 后台容器仍显示运行数周

这是正常结果。本次代码只修改聊天和搜索 API。

无需重启后台索引任务。

### 14B 仍然只回答少量案例

先检查 `rag_search_pipeline` 日志。

如果 `selected` 足够大，但答案仍然很短，则问题位于最终生成阶段。

检查 `num_predict`、系统提示词和回答格式要求。

如果 `retrieved_chunks` 很小，则问题位于召回或索引阶段。

检查数据源同步、索引状态、关键词和 embedding 配置。

### 模型出现上下文溢出

确认 Onyx Max input tokens 与 Ollama `num_ctx` 一致。

降低 `SEARCH_CONTEXT_TOKEN_RESERVE` 不会解决模型真实上限不足的问题。

优先减少上下文片段，或改用 20K 模型。
