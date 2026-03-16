# DataAgent Multi-turn Verification

Use the standalone verifier script to validate the real Ferry `DataAgent` path instead of calling `SkillCreatorAgent` directly.

## Run

```bash
cd /Users/weichong/Documents/new_working_area/skill-creator-agent
uv run python scripts/verify_data_agent_multiturn.py
```

The script will:

- build a `SkillCreatorRuntime`
- materialize a Ferry YAML config
- initialize `ferry.interface.sdk.agent.DataAgent`
- reuse the same `session_id` across turns
- increment `run_id` automatically

## Useful options

```bash
uv run python scripts/verify_data_agent_multiturn.py \
  --skills-root /Users/weichong/Documents/new_working_area/skill-creator-agent/skills \
  --graph-base-url http://127.0.0.1:8000
```

Run a fixed scripted conversation:

```bash
uv run python scripts/verify_data_agent_multiturn.py \
  --turn "先列出图数据库中的对象类型" \
  --turn "继续解释 KpiOfDailyPersonalBusinessLoan 的关键字段" \
  --turn "基于前两轮内容设计一个 skill 草案"
```

## REPL commands

- `/skills`: print current runtime skills
- `/config`: print the rendered Ferry YAML path
- `/reset`: start a fresh multi-turn session with a new `session_id`
- `/quit`: exit
