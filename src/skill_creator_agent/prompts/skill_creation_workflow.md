# Skill Creation Workflow

Follow these steps in order when no existing skill can satisfy the request.

## Step 1: Confirm Skill Creation Need
- Tell the user explicitly that no matching skill exists yet.
- Ask whether they want you to create a new skill for this purpose.
- Do not gather documents, inspect graph data, propose an execution plan, or create files in this step.

**STOP HERE. Wait for the user's response.**

## Step 2: Gather Reference Documentation
If the user wants a new skill:
- Ask whether they have reference documentation, sample commands, schemas, examples, or business rules that should guide the skill.
- If they do, ask them to provide the file path or paste the content.
- If they do not, accept that answer and continue without inventing documentation.
- Do not inspect graph data or create files in this step.

**STOP HERE. Wait for the user's response.**

## Step 3: Query Required Graph Schema
After the user answers the documentation question:
- If graph tools are available and relevant, inspect only the schema and sample data required for the requested skill.
- Start with:
  - `graph_get_object_types()`
  - `graph_get_object_relations()`
- For each required entity, inspect:
  - `graph_get_entity_schema(entity_type=...)`
  - `graph_query_examples(entity_type=..., limit=3)`
- Record only the fields, UUID patterns, and relationships that are necessary for the skill design.

## Step 4: Present Execution Plan For Approval
Present a concise but concrete plan that includes:
- proposed skill name
- what the skill will do
- which graph entities or external references it depends on
- which scripts or reference files will be created
- what inputs and outputs the skill will support

Then ask:
"Does this execution flow look correct? Should I proceed with creating the skill, or would you like me to adjust anything?"

**STOP HERE. Wait for the user's explicit approval. Do not create any files yet.**

## Step 5: Create Complete Skill Package
Only after explicit approval:
- create `SKILL.md`
- create the required scripts under `scripts/`
- create only the references that are actually needed
- keep the skill production-ready rather than leaving a placeholder template

## Step 6: Reload And Confirm Execution
After creating the package:
- reload the new skill
- summarize what was created
- ask whether the new skill should now be executed against the original request
