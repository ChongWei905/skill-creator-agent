# Workflow-Svc -> Ferry Agent Migration Todo

当前代码已从 `ferry` 仓库中迁出，现落地在：
`/Users/weichong/Documents/new_working_area/skill-creator-agent`

## Goal

将 `/Users/weichong/Documents/new_working_area/workflow-svc` 中“生成和执行 skill”的核心逻辑迁移为 `ferry` 中的一个专用子 agent，建议名称为 `skill_creator`。

迁移目标不是复制 `workflow-svc` 的 CLI 或 LLM 外壳，而是：

- 复用 `ferry` 的 agent 生命周期、工作流和工具调度
- 迁移 `workflow-svc` 的 skill runtime 领域逻辑
- 支持在共享 skill 目录上完成：
  - 发现 skill
  - 读取 `SKILL.md`
  - 列出脚本
  - 执行脚本
  - 创建新 skill
  - reload 新 skill

---

## Current Anchoring Snapshot (2026-03-13)

### Workflow-Svc

- 已在 `/Users/weichong/Documents/new_working_area/workflow-svc/.venv` 创建独立环境
- 已安装 `requirements.txt`
- `python skill_executor_main.py --list` 可正常列出 skills
- `printf 'quit\n' | python skill_executor_main.py -i` 可启动交互模式
- `pytest tests/unit/test_main.py -q` 通过
- `pytest tests -q` 通过，当前基线为 `250 passed`
- 当前 `config.yaml` 中图数据库配置存在，但实际探活返回 `503`
- 当前 `config.yaml` 中存在真实 API key，迁移前应改为环境变量注入

### Ferry

- 已修复 `/Users/weichong/Documents/new_working_area/ferry/.venv`
- 由于本地 shell 会被 conda 污染，后续统一使用显式解释器：
  - `/Users/weichong/Documents/new_working_area/ferry/.venv/bin/python`
- `pip install -e .` 需使用镜像源，推荐：

```bash
cd /Users/weichong/Documents/new_working_area/ferry
.venv/bin/python -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

- `.venv/bin/python -m ferry --help` 可运行
- `.venv/bin/python -c 'import httpx, cv2'` 可运行
- `from ferry.actions.tools.local_tool import tools` 可导入，但首次导入较慢，并会提示缺少 `.env`

---

## Phase 0: Pre-Dev Anchoring

### 0.1 Confirm Scope and Naming

- [x] 确认新 agent 名称，统一使用 `skill_creator`
- [x] 确认 `AGENT_CONFIG.agent_type` 取值为 `skill_creator`
- [x] 确认共享 skill 根目录的唯一配置来源
- [x] 确认图数据库是否是该 agent 的必选依赖，还是可选能力

当前决策：
- 领域 agent 名称统一为 `skill_creator`
- 最终配置入口统一使用 `AGENT_CONFIG.agent_type: skill_creator`
- skill runtime 的根目录不复用 `TOOLS.skills` 作为配置来源，单独使用 `SKILL_CREATOR.skills_root`
- 环境变量覆盖使用 `SKILL_CREATOR_SKILLS_ROOT`
- 图数据库不是开发和迁移前提；`skill_creator` 第一阶段按“graph 可选扩展”设计

### 0.2 Verify Local Repos and Paths

- [x] 确认两个工作区都可正常访问：
  - `/Users/weichong/Documents/new_working_area/ferry`
  - `/Users/weichong/Documents/new_working_area/workflow-svc`
- [x] 确认 `workflow-svc` 中的关键资产存在：
  - `skills/`
  - `prompts/`
  - `models/skill.py`
  - `loaders/skill_loader.py`
  - `connectors/graph_connector.py`
  - `executor/skill_executor.py`
- [x] 确认 `ferry` 中的关键接入点存在：
  - `ferry/interface/sdk/agent.py`
  - `ferry/core/flex/`
  - `ferry/actions/tools/local_tool/tools.py`
  - `ferry/agents/`

### 0.3 Build a Reproducible Workflow-Svc Dev Environment

- [x] 在 `workflow-svc` 根目录创建独立虚拟环境
- [x] 安装依赖：

```bash
cd /Users/weichong/Documents/new_working_area/workflow-svc
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

- [ ] 准备配置文件：

```bash
# 如果仓库提供的是 config.yaml.example
cp config.yaml.example config.yaml

# 如果仓库已经直接提供 config.yaml
cp config.yaml config.local.yaml
```

- [ ] 清理 `config.yaml` 中的敏感信息，优先改为环境变量读取
- [ ] 设置最小环境变量：

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.deepseek.com"
```

- [ ] 如果需要 Anthropic，额外设置：

```bash
export ANTHROPIC_API_KEY="..."
```

### 0.4 Prove Workflow-Svc Can Run End-to-End

- [x] 先确认 skill 能被扫描：

```bash
cd /Users/weichong/Documents/new_working_area/workflow-svc
.venv/bin/python skill_executor_main.py --list
```

- [x] 再验证交互式模式可启动：

```bash
.venv/bin/python skill_executor_main.py -i
```

- [ ] 再验证最小单轮请求可走通：

```bash
.venv/bin/python skill_executor_main.py "创建一个查询基金信息的 skill" --verbose
```

- [ ] 记录以下信息到开发笔记：
  - 使用的 provider
  - 使用的 model
  - 是否依赖 graph API
  - 哪个已有 skill 会被匹配
  - 哪个 prompt 分支会触发 skill creation

### 0.5 Prove Workflow-Svc Tests Can Run

- [x] 运行最小测试集，确保后续迁移有对照基线：

```bash
cd /Users/weichong/Documents/new_working_area/workflow-svc
.venv/bin/python -m pytest tests/unit/test_main.py -q
.venv/bin/python -m pytest tests -q
```

- [x] 记录当前测试是否全绿
- [x] 如果有失败，区分是环境问题还是代码问题

### 0.6 Prepare Ferry Dev Environment

- [x] 在 `ferry` 根目录同步依赖：

```bash
cd /Users/weichong/Documents/new_working_area/ferry
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

- [x] 验证 `ferry` 的最小入口可运行：

```bash
.venv/bin/python -m ferry --help
```

- [x] 验证已有 `FlexAgent` 示例配置可被读取
- [x] 确认 `read_file`、`write_file`、`bash`、`apply_patch` 这类本地工具在 `ferry` 中可用

### 0.7 Establish a Fast Debug Loop

- [x] 确定后续开发采用“边迁移边验证”的闭环：
  - 改一个模块
  - 写一个最小测试
  - 跑一个最小配置
  - 再迁移下一块
- [x] 先准备一个最小调试用 skill 根目录
- [x] 先准备一个最小调试用 `skill_creator_agent.yaml`
- [x] 先准备一个最小 smoke test，目标仅验证：
  - 能加载一个 skill
  - 能读取 `SKILL.md`
  - 能列出脚本

已落地的调试资产：
- 最小 skill fixture：`src/skill_creator_agent/fixtures/minimal_skills/skill-creator-smoke/`
- 预接入调试配置：`src/skill_creator_agent/skill_creator_debug.yaml`
- smoke test：`tests/skill_creator/test_phase0_smoke.py`

说明：
- 在 `select_engine()` 正式接入前，调试配置仍然走 `type: react`
- 同时保留 `agent_type: skill_creator`，这样配置语义已与未来正式 agent 对齐

### 0.8 Decide Shared Skill Directory Strategy

- [x] 确定 `workflow-svc` 和 `ferry/skill_creator` 共用同一 skill 根目录
- [x] 确定该目录如何配置，建议优先级如下：
  - agent YAML
  - 环境变量
  - 默认路径
- [x] 确认共享目录满足统一格式：
  - `SKILL.md`
  - `scripts/`
  - 可选 `references/`
  - 可选 `assets/`
- [x] 确认 `SKILL.md` 的 frontmatter 校验规则将被保留

当前决策：
- 本地联调时，`workflow-svc` 与未来的 `skill_creator` 共享外部目录 `/Users/weichong/Documents/new_working_area/workflow-svc/skills`
- 仓库内测试和 smoke 验证不直接依赖父目录项目，统一使用 `src/skill_creator_agent/fixtures/minimal_skills/`
- `SKILL_CREATOR.skills_root` 的优先级为：
  - YAML 显式配置
  - 环境变量 `SKILL_CREATOR_SKILLS_ROOT`
  - 项目根目录 `skills/`
- `TOOLS.skills` 只继续承担 prompt 注入用的 skill 元数据，不作为 `skill_creator` runtime 的唯一事实来源
- 共享 skill 目录的最小契约保持为：
  - skill 目录名与 frontmatter `name` 一致
  - 必有 `SKILL.md`
  - `scripts/` 下只放可执行脚本资源
  - frontmatter 至少保留 `name`、`description`

## Next Stage

当前已完成：

1. 创建能力闭环的基础版本
   - `SkillCreatorRuntime.create_skill_scaffold(...)` 已支持创建 skill 目录、写入 `SKILL.md`、初始化 `scripts/`
   - `reload_skill(...)` 已可重新加载新建 skill

2. `ferry` bridge 的最小接入
   - 已新增 `skill_creator_agent.ferry_tools`，把 skill runtime 能力暴露成 `ferry` 可注册的 `local_functions`
   - 已新增 `skill_creator_agent.ferry_config`，可生成兼容 `DataAgent/FlexAgent` 的配置
   - `SkillCreatorAgent` 已直接继承 `ferry.core.flex.agent.FlexAgent`，不再停留在 facade/wrapper 形态
   - `SkillCreatorAgent.from_config(...)` 会先装配 runtime/tools，再返回真正可 `chat/astream` 的 `FlexAgent` 子类实例

3. 创建链路测试
   - 已覆盖新建 scaffold、reload、以及 `ferry.actions.tools.manager.ToolManager` 注册调用自定义工具的集成测试

当前测试基线：
- `uv run python -m pytest tests/skill_creator -q`
- 结果：`22 passed`

剩余阶段建议按下面顺序推进：

1. 强化创建链路
   - 为 scaffold 结果补充更细的目录约束和错误信息
   - 增加对 `references/`、`assets/`、可选 `agents/openai.yaml` 的生成支持
   - 增加非法 script 路径、非法 frontmatter 的更细测试

2. 区分运行目录与测试目录
   - 真实运行默认使用项目根目录 `skills/`
   - 测试和 smoke fixture 继续使用 `src/skill_creator_agent/fixtures/minimal_skills/`
   - 为新创建的 skills 增加基本目录契约校验

3. 接入真实 LLM 驱动 loop
   - 直接使用 `SkillCreatorAgent.from_config(...)` 返回的 agent 实例
   - 用真实模型配置手动验证：
     - skills 元数据注入
     - `create_skill_scaffold -> write_file/apply_patch -> reload_skill -> execute_skill_script`
     - 多轮对话下的新 skill 是否可继续执行

4. 补更高层的集成测试
   - `DataAgent.from_config(...)` 级别的配置装配测试
   - 真实模型可用时再补对话级 smoke
   - graph 相关能力继续保持可选，不作为主链前提
   - 脚本写入后可被 loader 发现
   - reload 后新 skill 可见

5. 最后再考虑如何与上层系统集成
   - 保持当前仓库是独立 package
   - 通过依赖 `ferry` 的方式被上层项目引用，而不是反向把代码塞回 `ferry`

---

## Phase 1: Migration Design

### 1.1 Define What Will and Will Not Be Migrated

- [ ] 明确迁移的模块：
  - `models/skill.py`
  - `loaders/skill_loader.py`
  - `connectors/graph_connector.py`
  - `prompts/*.md`
  - `executor/skill_executor.py` 中的领域行为
- [ ] 明确不迁移的模块：
  - `skill_executor_main.py`
  - `workflow-svc/llm/*`
  - `workflow-svc` 自己的手写 tool-calling while loop

### 1.2 Define Ferry-Side Target Layout

- [ ] 创建目标目录：

```text
src/skill_creator_agent/
  agent.py
  skill_creator_agent.yaml
  models/
  loaders/
  connectors/
  prompts/
  tools.py
```

- [ ] 确定哪些文件是 agent 私有模块
- [ ] 确定哪些能力注册为 `TOOLS.local_functions`

### 1.3 Define Runtime Boundary

- [ ] 明确 `ferry` 提供：
  - LLM 管理
  - actor/executor 工作流
  - tool 调度
  - agent 初始化
- [ ] 明确 `skill_creator` agent 提供：
  - skill 模型
  - skill loader
  - graph connector
  - skill domain tools
  - prompts

---

## Phase 2: Implement the Agent Skeleton

### 2.1 Create the Agent Directory

- [x] 新建 `src/skill_creator_agent/`
- [x] 添加 `__init__` 所需导出
- [x] 新建 `agent.py`
- [x] 新建 `skill_creator_agent.yaml`

### 2.2 Implement a Thin Agent Wrapper

- [x] 参考 `ferry/agents/deep_analysis/agent.py`
- [x] 在 `agent.py` 中实现 `SkillCreatorAgent.from_config(...)`
- [x] 确保该 agent 底层仍然走 `FlexAgent`
- [x] 在必要时注入默认 scenario 和运行配置

### 2.3 Register Agent Type

- [ ] 修改 `ferry/interface/sdk/agent.py`
- [ ] 在 `select_engine()` 中增加 `agent_type == "skill_creator"` 分支
- [ ] 验证 `DataAgent.from_config()` 可以加载新 agent

---

## Phase 3: Migrate Workflow-Svc Domain Modules

### 3.1 Migrate Skill Models

- [ ] 迁移 `workflow-svc/models/skill.py`
- [ ] 保留：
  - `Skill`
  - `SkillScript`
  - `to_metadata_context`
  - `to_full_context`
  - 脚本执行封装
- [ ] 调整 import 和路径推导逻辑，使其符合 `ferry` 目录结构

### 3.2 Migrate Skill Loader

- [ ] 迁移 `workflow-svc/loaders/skill_loader.py`
- [ ] 保留 frontmatter 校验
- [ ] 保留脚本发现逻辑
- [ ] 改成 agent 私有 loader，不依赖 `workflow-svc` 的包路径

### 3.3 Migrate Graph Connector

- [ ] 迁移 `workflow-svc/connectors/graph_connector.py`
- [ ] 确认它只依赖 `requests`
- [ ] 为 graph base URL 和 timeout 增加 `ferry` 配置读取方式

### 3.4 Migrate Prompts

- [ ] 迁移以下 prompt 到 `src/skill_creator_agent/prompts/`
  - `system_prompt_base.md`
  - `skill_creation_workflow.md`
  - `graph_db_instruction.md`
  - `skill_execution_reminder.md`
  - `no_skill_fallback.md`
  - 可选 `no_skill_fallback_direct.md`
- [ ] 改造 prompt 中的占位符，使其适配 `ferry` 的 prompt 模板机制

---

## Phase 4: Convert Workflow-Svc Behaviors into Ferry Tools

### 4.1 Remove the Handwritten Tool Loop

- [ ] 不迁移 `SkillExecutor.execute()` 中的主循环
- [ ] 只提取其中的领域行为方法

### 4.2 Implement Skill Runtime Tools

- [ ] 将以下行为实现为 `ferry` local tools：
  - `read_skill_content`
  - `list_skill_scripts`
  - `read_script_source`
  - `execute_skill_script`
  - `reload_skill`

### 4.3 Implement Graph Query Tools

- [ ] 将以下行为实现为 `ferry` local tools：
  - `graph_get_object_types`
  - `graph_get_object_relations`
  - `graph_get_entity_schema`
  - `graph_query_examples`
  - `graph_property_filter`
  - `graph_property_info`
  - `graph_hop_search`
  - `graph_count_search`

### 4.4 Reuse Existing Ferry File Tools

- [ ] 直接复用：
  - `read_file`
  - `write_file`
  - `bash`
  - `apply_patch`
- [ ] 不重复迁移 `workflow-svc` 自己的 `write_file`

### 4.5 Wire Tools into YAML

- [ ] 在 `skill_creator_agent.yaml` 中注册以上 local tools
- [ ] 确保该 agent 能同时访问：
  - 共享 skill 根目录
  - 输出目录
  - 可选 graph API

---

## Phase 5: Make the Prompts Work Inside Ferry

### 5.1 Build the Skill Metadata Context

- [ ] 为 `skill_creator` agent 增加“当前已存在 skill 列表”的 prompt 注入能力
- [ ] 只注入 Level 1 元数据，不要一开始注入完整 `SKILL.md`

### 5.2 Recreate the Workflow-Svc Prompt Semantics

- [ ] 保留 “无匹配 skill -> 进入 skill creation workflow” 语义
- [ ] 保留 “先确认 -> 再收集文档 -> 再查 graph schema -> 再展示计划 -> 再创建 skill” 的流程
- [ ] 保留 “创建后提醒用户是否执行新 skill” 的语义

### 5.3 Ensure Tool Usage Order Is Constrained

- [ ] 在 prompt 中强约束 graph 工具必须在正确步骤后调用
- [ ] 在 prompt 中强约束创建 skill 后必须 reload
- [ ] 在 prompt 中强约束 reload 成功后再执行脚本

---

## Phase 6: Debugging and Validation While Developing

### 6.1 Add Smoke Tests Early

- [ ] 先写最小单测：
  - loader 能解析合法 `SKILL.md`
  - loader 会拒绝非法 frontmatter
  - `execute_skill_script` 能运行一个测试脚本
  - `reload_skill` 能把新 skill 注入运行态

### 6.2 Add Agent-Level E2E Tests

- [ ] 写最小 agent 配置测试
- [ ] 验证 `DataAgent.from_config()` 能实例化 `skill_creator`
- [ ] 验证一次最小 query 能触发至少一个 skill-domain tool

### 6.3 Create a Manual Debug Script

- [ ] 准备一个最小调试命令，便于边开发边跑：

```bash
cd /Users/weichong/Documents/new_working_area/ferry
uv run -m ferry path/to/skill_creator_agent.yaml
```

- [ ] 或准备一个最小 `run.py`，直接加载 `DataAgent.from_config(...)`

### 6.4 Keep a Stable Debug Fixture Set

- [ ] 保留至少 3 个固定 skill 用例：
  - 纯文件型 skill
  - 带脚本执行的 skill
  - 带 graph 查询依赖的 skill
- [ ] 保留一个最小新建 skill 用例，用于验证 create -> reload -> execute 闭环

---

## Phase 7: Acceptance Criteria

### 7.1 Functional Acceptance

- [ ] `skill_creator` agent 能加载共享 skill 目录
- [ ] agent 能只基于 metadata 判断已有 skill 是否匹配
- [ ] agent 能按需读取完整 `SKILL.md`
- [ ] agent 能列出指定 skill 的脚本
- [ ] agent 能执行指定脚本并返回结果
- [ ] agent 能创建一个新的 skill 包
- [ ] agent 能 reload 新 skill
- [ ] agent 能在 reload 后执行新 skill 解决原始问题

### 7.2 Engineering Acceptance

- [ ] 不引入 `workflow-svc` 自己的 LLM adapter
- [ ] 不保留双层 tool-calling loop
- [ ] skill root 路径配置清晰且可覆盖
- [ ] 关键路径有测试覆盖
- [ ] 最小手工调试链路稳定

### 7.3 Migration Acceptance

- [ ] 对照 `workflow-svc`，确认以下能力已经在 `ferry` 侧可用：
  - skill 解析
  - skill 执行
  - graph 查询
  - skill 创建
  - skill reload
- [ ] 确认后续可以废弃 `workflow-svc` 作为独立运行入口，或至少不再依赖其 CLI

---

## Suggested Execution Order

- [ ] 先完成 Phase 0
- [ ] 再做 agent skeleton
- [ ] 再迁 models / loader / connector
- [ ] 再把 runtime behavior 改写为 ferry tools
- [ ] 再接 prompts
- [ ] 再跑 smoke tests
- [ ] 最后做完整 e2e 和后端接入
