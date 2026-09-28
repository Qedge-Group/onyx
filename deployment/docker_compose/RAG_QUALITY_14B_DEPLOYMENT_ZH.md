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

## 6. Ollama 14B 模型配置

### 6.1 创建 20K 模型

在 Ollama 服务器创建 `Modelfile`：

```text
FROM qwen3:14b

PARAMETER num_ctx 20480
PARAMETER temperature 0.1
PARAMETER num_predict 1024

SYSTEM 你是一个基于知识库检索结果回答问题的助手。只根据提供的知识库内容回答。资料不足时明确说明，不得编造。回答需要保留来源引用。
```

创建模型：

```bash
ollama create qwen3-custom:14b-20k -f Modelfile
ollama list
```

运行一次模型：

```bash
ollama run qwen3-custom:14b-20k '请回答：测试成功'
```

查看 GPU 显存：

```bash
nvidia-smi
ollama ps
```

不要把 Ollama 的 `11434` 端口直接暴露到公网。

应使用内网、VPN、安全组或防火墙限制访问来源。

### 6.2 在 Onyx 中添加模型

在 Onyx 管理界面打开 LLM Provider 设置。

添加 Ollama Provider，并填写以下值：

| 项目 | 值 |
| --- | --- |
| Provider | Ollama |
| Base URL | `http://Ollama内网地址:11434` |
| Model name | `qwen3-custom:14b-20k` |
| Max input tokens | `20480` |

Onyx 的 Max input tokens 必须与 Ollama 的 `num_ctx` 一致。

不要为 20K 模型填写 `262144`。过大的值会增加 KV Cache 和显存占用。

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
