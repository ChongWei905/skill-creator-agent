---
name: skill-creator-smoke
description: Use this fixture only when validating that the migrated skill_creator agent can discover a skill package, read SKILL.md, and enumerate bundled scripts.
---

# Skill Creator Smoke

## When to use

Use this fixture only for migration smoke tests of the `skill_creator` agent.

## Validation steps

1. Read this file to verify the skill package is discoverable.
2. Confirm the `scripts/echo_input.sh` file is present.
3. Optionally run the script with a short string to verify script wiring.
