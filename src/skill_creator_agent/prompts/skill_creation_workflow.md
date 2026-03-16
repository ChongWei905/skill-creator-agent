# Skill Creation Workflow

Follow these steps in order when no existing skill can satisfy the request:

1. Tell the user that no matching skill currently exists.
2. Confirm whether they want a new skill to be created.
3. Gather any reference documents, sample commands, schemas, or business rules that the skill should encode.
4. If graph tools are available and relevant, inspect only the required graph schema before finalizing the skill design.
5. Present a short execution plan for approval:
   - proposed skill name
   - what the skill will do
   - which scripts or references will be created
   - what inputs and outputs the skill will support
6. After approval, create a complete skill package:
   - `SKILL.md`
   - required scripts under `scripts/`
   - only the references that are actually needed
7. Reload the new skill and ask whether it should be executed against the original request.
