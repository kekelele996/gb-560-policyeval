# policyeval · 容器与 K8s 策略合规评估台

把「写在 Confluence 里的合规策略」变成**可机读、可机器校验、可审计闭环**的 DSL，对 GitOps 导出的 K8s 清单做真实求值，对资源规约做真实配额聚合，产出带 evidence 的违规清单、patch 建议、豁免审批与合规报告。

模拟客户：**澜川银行 · 云原生平台部**（3 个生产集群 / 220 个命名空间 / 60 个业务系统，等保 2.0 + CIS Benchmark 双合规）。

> 数据说明：仓库内清单、策略、运行、违规全部为**合成数据**，不连接真实 K8s 集群、GitOps 仓库、审计平台或 CI；算法对合成清单真算，但不对真实资产做扫描。

## 1. 场景与工作流

| 维度 | 内容 |
|---|---|
| 现有工作流 | 策略写在 Confluence wiki；平台工程师每季度用 kubectl 抽查 20 个 ns，手工整理 Excel 整改单；等保审计前突击一个月 |
| 三个痛点 | ① 策略是人读的 wiki，无法对 220 ns 的清单机器校验；② 同一违规跨命名空间重复 40 次，整改无从下手；③ 整改没有 owner 与到期跟踪，审计前才发现 30% 未闭环 |
| 上游 | GitOps 仓库导出的多文档 K8s YAML 清单 + 集群配额快照 |
| 本系统替代 | Confluence 策略 + 人工抽查 + Excel 整改单 |
| 下游 | 业务团队 patch（GitOps 合入）+ 审计报告（Markdown 导出）+ 豁免审批记录 |

角色权限（三演示账号，密码统一 `Demo@2026`）：

| 角色 | 账号 | 主要页面 | 权限 |
|---|---|---|---|
| admin | `admin@policyeval.demo` | 全部 | 全部读写 + 豁免审批 + 审计日志 |
| engineer | `engineer@policyeval.demo` | 清单/策略/评估/违规 | 导入清单、写策略、跑评估、生成 patch |
| owner | `owner@policyeval.demo` | 违规（仅本 ns）/豁免 | 只读 `lc-payments`、`lc-ml-serving` + 确认整改 + 申请豁免 |

## 2. 两个核心算法（Python 服务层真算并落库）

### 算法 1：策略 DSL 手写词法器 + 递归下降解析器 + 文档树求值

- 代码：`backend/src/services/dsl_parser.py`（词法/语法/诊断）、`backend/src/services/dsl_eval.py`（求值/证据）。
- 语法：`all(...) / any(...) / not(...)`；谓词 `path op value`、`hasKey(path)`、`count(path) op number`、`startsWith(path, "...")`、`matches(path, "regex")`；路径支持 `spec.containers[].resources.limits.cpu`、`[0]`、`[*]`；字面量支持字符串/数字（含 `500m`、`1Gi` 等 K8s quantity）/bool/null。
- 解析失败返回 **行号、列号、期望 token 列表、源码片段**；成功把 `{ast, predicate_count, path_count, max_depth, summary}` 落到 `policy_rules.ast_json`。
- 求值在 PyYAML `safe_load` 出来的文档树上按路径展开叶子：每条违规 evidence 记录 `path / actual / expected / passed / note`；`all/any` 短路。
- **禁止 eval()/exec()**：求值器只遍历显式 AST 节点（`_eval_compare/_eval_has_key/_eval_count/_eval_string_fn`）。
- 失败态：未知字段 → `false` + `missing_field` warning；类型不匹配 → `type_mismatch`；K8s quantity 字符串与数字比较时做一次受控折算（`coerced_quantity`），不算类型错误。
- 量词语义：`compare / hasKey / count` 对通配符展开是**全称**（每个叶子都要满足）；`startsWith / matches` 是**存在**（任一叶子命中即成立，用于「任意容器使用 latest」这类检测）。该口径在 `dsl_eval.py` 文件头与 API evidence 里同步标注。

### 算法 2：资源规约聚合与配额判定

- 代码：`backend/src/services/quota.py`。
- quantity 解析：`500m → 0.5`、`2 → 2`、`1Gi → 1073741824`、`512Mi → 536870912`、`1e3 → 1000`；非法/负数 → 0 并记 warning。
- 聚合：按 namespace 汇总 `requests.cpu / requests.memory / limits.cpu / limits.memory`；Deployment/StatefulSet 按 `spec.replicas` 加权（缺省 1 并记 warning）；同一 `(kind, ns, name)` 重复定义取最后一次并记 warning。
- 判定：`used > threshold` 判超配额；threshold 优先级 `ResourceQuota.hard` → `LimitRange.max` → 平台默认阈值（`PLATFORM_QUOTA_*` 环境变量）；另外判 `requests > limits` 与 `limits` 缺失。
- 超限严重度：`ratio >= 1.5 → critical`、`>= 1.2 → high`、`> 1.0 → medium`；输出 CPU 双单位（核 / m）与内存双单位（字节 / GiB）。
- 结果落库：超配额与 requests>limits 进入 `violations`（`source=quota`，`policy_id` 为空、`rule_code=QUOTA-OVER / QUOTA-REQ_GT_LIMIT`），`ns_summary` 随运行详情返回给前端聚合页。

两个算法都在 **Celery worker 容器**中由任务 `policyeval.evaluate_run` 执行，运行记录、违规、证据全部落 MySQL；前端只做展示与交互。

## 3. 页面

| 路由 | 页面 | 说明 |
|---|---|---|
| `/login` | 值班登录 | 左侧客户/工作流背景，右侧账号登录 |
| `/bundles` | 清单包解析 | 左侧 YAML 原文（可点文档切换）/ 右侧 120 文档树（kind/name/ns），支持导入新清单 |
| `/policies` | 策略编辑器 | DSL 编辑 + 实时解析错误行列 + AST 摘要 + 试运行命中数；保存 bump 版本 |
| `/runs` | 评估运行 | 发起真实评估（worker 执行、轮询状态）、规则通过率、严重度分布 |
| `/violations` | 违规清单 | severity/namespace 聚合热度、evidence 字段路径与实际数值、生成 patch 建议、申请豁免 |
| `/exemptions` | 豁免与合规报告 | admin 审批豁免、合规分、Markdown 报告导出 |

三栏「调度管制台」布局：左侧管制席位导航 240px / 中间主工作区 / 右侧状态灯与计数；深墨绿底 + 米色面板；信号灯三色只用于状态。

## 4. 快速启动

```bash
cd batch-20261110c/projects/gb-560
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose ps            # 5/5 healthy（约 60-120s）

# seed 幂等；backend 启动时 SEED_DEMO=true 已自动跑过一次
docker compose exec -T backend python -m scripts.seed_demo   # 期望输出 SEED_SUMMARY users=3 bundles=1 policies=9 runs=3 violations=140 exemptions=6 advices=3

# 收尾
docker compose down -v --remove-orphans
```

访问：

| 入口 | 地址 |
|---|---|
| 前端 | http://localhost:18233 |
| 后端 OpenAPI | http://localhost:19233/docs |
| 健康检查 | http://localhost:19233/api/health |
| MySQL | `127.0.0.1:17733`（user `policyeval` / 密码见 `.env`） |

本地开发（可选）：后端 `cd backend && pip install -r requirements.txt && uvicorn src.main:app --port 8000`；前端 `cd frontend && npm install && npm run dev`（Vite 代理 `/api` 到 19233）。

## 5. 技术栈

| 层 | 技术 |
|---|---|
| frontend | React 18 + TypeScript 5 + Vite 5 + React Router 6 + Zustand 4；Nginx 1.27 托管 |
| backend | Python 3.11 + FastAPI 0.115 + SQLAlchemy 2.0 + Alembic + PyJWT + PyYAML |
| worker | Celery 5.4（Redis broker，执行评估任务 + beat 心跳） |
| db | MySQL 8.0（utf8mb4） |
| cache | Redis 7（限流 / 每日配额 / worker 心跳） |

## 6. 目录

```
gb-560/
├── docker-compose.yml            # 顶层 name: policyeval，无 version
├── .env.example / .env
├── backend/
│   ├── Dockerfile / requirements.txt / entrypoint.sh / alembic.ini
│   ├── migrations/               # alembic（0001_initial 走 Base.metadata.create_all）
│   ├── scripts/                  # seed_data.py（120 文档生成器）/ seed_demo.py（幂等 seed）
│   └── src/
│       ├── config/               # settings / database / celery_app / app
│       ├── constants/            # enums.py（共享枚举）/ roles.py / error_codes.py
│       ├── models/               # 6 实体 + user + audit_log
│       ├── schemas/              # auth / catalog / evaluation / governance / common
│       ├── services/             # dsl_parser / dsl_eval / quota + 各业务 service
│       ├── controllers/          # auth / catalog / evaluation / governance
│       ├── routes/               # auth / catalog / evaluation / governance / system
│       ├── middlewares/          # auth / rbac / rate_limit / audit_logger / error_handler
│       └── utils/                # errors / jwt / password / logger / redis_client
├── worker/                       # worker_src：celery_app + evaluate_task + heartbeat_task
└── frontend/
    └── src/{api,stores,types,components/{common,business,layout},hooks,pages,router,utils,constants,styles}
```

## 7. 环境变量（`.env.example`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | policyeval | 容器名前缀 |
| `FRONTEND_PORT` / `BACKEND_PORT` / `DB_PORT` | 18233 / 19233 / 17733 | 题目分配端口 |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_ROOT_PASSWORD` | policyeval / … | MySQL 账号 |
| `JWT_SECRET` | … | HS256 签名密钥（演示值，生产必须替换） |
| `REDIS_URL` | redis://redis:6379/0 | 限流 + Celery broker |
| `SEED_DEMO` | true | 启动时幂等 seed 一次，失败只记日志 |
| `RATE_LIMIT_PER_MINUTE` | 240 | 每用户每路由每分钟限流 |
| `DAILY_QUOTA_ADMIN/ENGINEER/OWNER` | 6000/3600/1800 | 每角色每日调用配额 |
| `PLATFORM_QUOTA_CPU_REQ` / `MEM_REQ_GIB` / `CPU_LIM` / `MEM_LIM_GIB` | 48/96/96/192 | 命名空间无 ResourceQuota 时的平台默认阈值 |

## 8. 共享枚举出现位置

| 枚举 | 后端定义 | 前端定义 | 出现位置 |
|---|---|---|---|
| `PolicySeverity`（low/medium/high/critical） | `backend/src/constants/enums.py` | `frontend/src/constants/enums.ts` | `models/policy_rule.py`、`services/quota.py`、`services/dsl_eval.py`、`schemas/evaluation.py`、`seed_demo.py`、`components/common/SeverityTag.tsx`、`pages/{Policies,Runs,Violations,Exemptions}.tsx` |
| `ViolationStatus`（open/exception/fixed） | 同上 | 同上 | `models/violation.py`、`services/{run,exemption,violation}_service.py`、`pages/Violations.tsx`、`components/common/StatusPill.tsx` 配合 |
| `ExemptionStatus`（pending/approved/rejected/expired） | 同上 | 同上 | `models/exemption.py`、`services/exemption_service.py`、`pages/Exemptions.tsx` |
| `RunStatus`（running/done/failed） | 同上 | 同上 | `models/evaluation_run.py`、`services/run_service.py`、`pages/Runs.tsx` |
| `RuleKind`（Pod/Deployment/Namespace/LimitRange） | 同上 | 同上 | `models/policy_rule.py`、`services/dsl_eval.py`、`pages/Policies.tsx` |
| `ViolationSource`（dsl/quota） | 同上 | 类型字面量 | `models/violation.py`、`services/quota.py`、`pages/Violations.tsx` |

共享前端组件：`SeverityTag`（违规页/报告）、`DslEditor`（策略页/试运行）、`EvidencePath`（策略试运行/违规详情）、`NsHeatBar`（违规聚合/合规报告）、`StatusPill`、`EmptyState`、`ParseTree`。

## 9. 演示数据

- 1 个 bundle「lanchuan-prod 2026Q4」：12 个命名空间 × 8-12 资源 = **120 个文档 / 12 个文件**，含 2 个 ResourceQuota、1 个 LimitRange、2 个故意超配额 ns（`lc-payments` 的 requests 维度、`lc-ml-serving` 的 limits 维度）、41 个缺 limits 的 Deployment。
- 9 条策略：7 条启用（5 条命中 + 2 条全部通过），2 条默认 disabled 的解析失败样本（缺右括号 / 未知函数 equals），用于展示错误行列诊断。
- 3 次评估运行：`seed-check-20261025`（单规则抽检，0 违规）、`seed-baseline-2026q4`（全量基线，140 违规）、`seed-running-20261110`（running）。
- 140 条违规：critical 12 / high 46 / medium 52 / low 30（由真实算法按清单数据算出，不是写死的行）。
- 6 条豁免：2 pending / 3 approved / 1 expired。
- 3 条预生成 patch 建议。

## 10. 已知差异与边界

1. **全部为合成数据，未连接真实 K8s 集群 / GitOps 仓库 / 审计系统**；「集群配额快照」就是仓库内 seed 生成的 YAML，patch 建议不会真正下发（需业务团队在 GitOps 仓库合入）。
2. 配额引擎对 `limits 缺失` 在 `ns_summary` 中计数并展示，但**不为它单独生成违规**——避免与 DSL 策略 `CIS-5.2.2` 对同一对象重复计数（口径见 `services/quota.py` 文件头）。
3. 豁免审批只做 single-step（admin 直接通过/驳回），没有多级审批流与豁免审计留痕附件；过期判断基于运行/审批时的服务器时间，无定时任务。
4. DSL 正则采用 `re.fullmatch` 语义并限制长度/嵌套量词（防灾难性回溯），不是完整 PCRE/K8s CEL 兼容实现；`matches` 对通配符路径是存在语义（见算法 1 口径）。
5. 演示规模 120 文档/140 违规，使用单 worker 串行执行，未做大规模分片；MySQL 单实例、单副本。

## 11. License

MIT（演示项目，仅用于内部评审与培训，不对真实银行资产做任何扫描或承诺）。
