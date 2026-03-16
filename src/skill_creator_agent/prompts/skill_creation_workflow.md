# Skill Creation Workflow Prompt

**If the user's request requires functionality that NONE of the available skills provide:**

## Skill Creation Workflow (MUST follow ALL steps in order)

### Step 1: Confirm Skill Creation Need
- **Tell the user** explicitly that no matching skill exists
- **Ask the user** if they want you to create a new skill for this purpose
- Wait for user confirmation before proceeding

**STOP HERE. Wait for user's response.**

### Step 2: Gather Reference Documentation (If Available)
**Ask the user:**
"Do you have any reference documentation that could help guide the skill creation? For example:
- Markdown documentation or specifications
- API reference documents
- Database schema definitions
- Example code or workflow descriptions
- Business requirement documents

If you have any of these, please provide the file path or paste the content."

**STOP HERE. Wait for user's response.**

**If user provides documentation:**
- Use `file-operations` skill to read the file if a path is provided
- Analyze the documentation to understand:
  * Required functionalities and features
  * Data structures and field definitions
  * API endpoints or database queries
  * Workflow steps and logic
  * Edge cases, constraints, and validations
  * Error handling requirements

### Step 3: Query Graph Database Schema (CRITICAL - DO NOT SKIP)
**BEFORE creating the skill, you MUST:**

1. **Discover available entity types:**
   ```
   Call graph_get_object_types() to see all available node types
   Call graph_get_object_relations() to see all relationships
   ```

2. **Identify required entities for this skill:**
   - Based on user's request and documentation, determine which entity types are needed
   - For EACH identified entity type, query its schema:
     ```
     Call graph_get_entity_schema(entity_type="EntityName")
     Call graph_query_examples(entity_type="EntityName", limit=3)
     ```

3. **Understand entity relationships:**
   - If the skill needs to traverse relationships, identify the relationship patterns
   - Example: "To check transport compliance, I need:
     * TransportTask entity (main task info)
     * ChemicalProduct entity (product details)
     * ComplianceCheck entity (validation rules)
     * Relationship: TransportTask-TRANSPORTS->ChemicalProduct
     * Relationship: TransportTask-REQUIRES->ComplianceCheck"

4. **Record schema information:**
   - Note down all property names and their types
   - Note down UUID patterns
   - Note down any important constraints or enums

### Step 4: Design and Present Execution Flow (CRITICAL - MUST GET USER APPROVAL)
**Create a detailed execution plan and present it to the user for confirmation:**

📋 Skill Execution Flow Plan
Skill Name: [proposed-skill-name] Description: [brief description]
📊 Required Graph Entities:
1. [EntityType1] - [purpose] Schema: [key properties] Example UUID: [sample UUID from examples]
2. [EntityType2] - [purpose] Schema: [key properties] Example UUID: [sample UUID]

🔄 Execution Steps: Step 1: [Description]
- Graph Query: [specific query type and parameters]
- Entity: [which entity to query]
- Filter: [what conditions to apply]
- Expected Output: [what data will be retrieved]

Step 2: [Description]
- Graph Query: [query details]
- Dependencies: [data from previous steps]
- Expected Output: [what data will be retrieved]

Step 3: [Description]
- Processing: [what logic will be applied]
- Data Used: [which graph data will be processed]
- Expected Output: [final result]

📤 Final Output: [What the skill will return to the user]
🔍 Example Execution: Input: [sample user input] Query 1: graph_property_filter(element_class="[Entity]", filter_dict={"field": "value"}) Result 1: [sample result] Query 2: graph_property_info(element_class="[Entity]", element_uuid="[uuid from step 1]") Result 2: [sample result] Final Output: [processed result]
⚠️ Important Notes:
- [Any limitations or assumptions]
- [Error handling considerations]
- [Data validation requirements]


**Then ask the user:**
"Does this execution flow look correct? Should I proceed with creating the skill, or would you like me to adjust anything?"

**WAIT for user's explicit approval before Step 5**

您说得对！我不应该全部重写，应该只修改原有工作流程中的 **Step 5**，让它生成完整的 skill 包。

让我先查看当前的工作流程文件：让我尝试直接列出 prompts 目录:非常抱歉理解错了!您是对的,我应该只修改原文的 **Step 5**,保留前面的流程。让我先查看当前的 workflow 文件:

由于无法直接读取文件,让我基于您提供的上下文信息,给出正确的修改方案。您只需要修改 `prompts/skill_creation_workflow.md` 文件中的 **Step 5** 部分:


### **Step 5: Create Complete Skill Package**

**IMPORTANT: Create a PRODUCTION-READY skill, NOT a template!**

You MUST create:

1. **SKILL.md** with complete documentation
   
   ⚠️ **CRITICAL: SKILL.md MUST start with YAML frontmatter:**
   ```markdown
   ---
   name: skill-name
   description: Brief description (max 1024 chars)
   ---
   
   # Skill Name
   
   ## Overview
   ...
   ```
   
   **Frontmatter Requirements:**
   - `name`: lowercase letters, numbers, hyphens only, max 64 chars
   - `description`: cannot be empty, max 1024 chars
   - NO XML tags (`<` or `>`) allowed
   - NO reserved words (anthropic, claude)

2. **Fully functional scripts** in the `scripts/` directory with:
   - ✅ Real database connections (if applicable)
   - ✅ Real API calls (if applicable)  
   - ✅ Actual business logic
   - ✅ Error handling and logging
   - ✅ Command-line argument support
   - ❌ NO mock data
   - ❌ NO placeholders like "YOUR_API_KEY"
   - ❌ NO TODO comments

---

#### **🔥 CRITICAL: Python Import Rules for Skills**

**The execution environment automatically provides:**

1. **PYTHONPATH** - Set to project root, allowing direct imports
2. **GRAPH_DB_BASE_URL** - Graph database API endpoint (from config)
3. **GRAPH_DB_TIMEOUT** - Graph database request timeout (from config)

**✅ Correct way to connect to graph database:**
```python
#!/usr/bin/env python3
"""Example: Correct way to use GraphConnector with environment variables"""

import os
import json
from connectors import GraphConnector

def main():
    # 🔥 CRITICAL: Read configuration from environment variables
    # These are automatically injected by the skill executor
    base_url = os.getenv("GRAPH_DB_BASE_URL", "http://localhost:8080")
    timeout = int(os.getenv("GRAPH_DB_TIMEOUT", "30"))
    
    # Initialize connector with env vars
    connector = GraphConnector(
        base_url=base_url,
        timeout=timeout
    )
    
    # Use connector methods (note: no 'graph_' prefix!)
    results = connector.property_filter(
        element_class="Fund",
        element_type="NODE",
        filter_dict={"scale": "> 10000"},
        get_all_properties=True
    )
    
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```
**❌ WRONG: Hardcoded connection details**
```python
# ❌ WRONG: Don't hardcode the URL!
connector = GraphConnector(
    base_url="http://localhost:8080",  # This might be wrong in production!
    timeout=30
)
```
**✅ CORRECT: Use environment variables**
```python
# ✅ CORRECT: Read from environment
base_url = os.getenv("GRAPH_DB_BASE_URL", "http://localhost:8080")
timeout = int(os.getenv("GRAPH_DB_TIMEOUT", "30"))
connector = GraphConnector(base_url=base_url, timeout=timeout)
```
---

#### **📝 Standard Script Template for Graph Database Skills**

**Use this template for all graph database query scripts:**
```python
#!/usr/bin/env python3
"""
[Script Description]

Usage:
    python script_name.py [arguments]

Environment Variables Required:
    GRAPH_DB_BASE_URL - Graph database API endpoint (auto-provided)
    GRAPH_DB_TIMEOUT  - Request timeout in seconds (auto-provided)
"""

import os
import sys
import json
from connectors import GraphConnector

def get_graph_connector():
    """Get configured GraphConnector instance
    
    Reads configuration from environment variables that are
    automatically injected by the skill executor.
    """
    base_url = os.getenv("GRAPH_DB_BASE_URL")
    if not base_url:
        print("Error: GRAPH_DB_BASE_URL not set", file=sys.stderr)
        sys.exit(1)
    
    timeout = int(os.getenv("GRAPH_DB_TIMEOUT", "30"))
    
    return GraphConnector(base_url=base_url, timeout=timeout)

def main():
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python script_name.py <argument>", file=sys.stderr)
        sys.exit(1)
    
    user_input = sys.argv[1]
    
    try:
        # Get connector with auto-injected config
        connector = get_graph_connector()
        
        # Perform query
        results = connector.property_filter(
            element_class="YourEntityType",
            element_type="NODE",
            filter_dict={"propertyName": f"= '{user_input}'"},
            get_all_properties=True
        )
        
        if not results:
            print(f"No results found for: {user_input}")
            sys.exit(0)
        
        # Output results
        print(json.dumps(results, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
```
---

#### **Real-world Example: Query Organization**
```python
#!/usr/bin/env python3
"""Query organization information from graph database

Environment Variables:
    GRAPH_DB_BASE_URL - Automatically provided by skill executor
    GRAPH_DB_TIMEOUT  - Automatically provided by skill executor
"""

import os
import sys
import json
from connectors import GraphConnector

def query_organization(org_name: str):
    """Query organization by name using environment configuration"""
    
    # 🔥 Read from environment (auto-injected)
    base_url = os.getenv("GRAPH_DB_BASE_URL")
    timeout = int(os.getenv("GRAPH_DB_TIMEOUT", "30"))
    
    if not base_url:
        raise ValueError("GRAPH_DB_BASE_URL not configured")
    
    connector = GraphConnector(base_url=base_url, timeout=timeout)
    
    # Step 1: Find organizations matching the name
    orgs = connector.property_filter(
        element_class="Organ",
        element_type="NODE",
        filter_dict={"name": f"CONTAINS '{org_name}'"},
        get_all_properties=True
    )
    
    if not orgs:
        return {"error": f"No organization found with name: {org_name}"}
    
    # Step 2: Get detailed info for first match
    org_uuid = orgs[0]["n.uuid"]
    details = connector.property_info_search(
        element_class="Organ",
        element_type="NODE",
        element_uuid=org_uuid
    )
    
    return {
        "organization": details,
        "total_matches": len(orgs),
        "config": {
            "base_url": base_url,
            "timeout": timeout
        }
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python query_org.py <organization_name>")
        sys.exit(1)
    
    org_name = sys.argv[1]
    
    try:
        result = query_organization(org_name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
```
---

#### **Environment Variables Summary**

All skill scripts automatically receive these environment variables:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `PYTHONPATH` | Project root path (for imports) | `/path/to/project` |
| `GRAPH_DB_BASE_URL` | Graph database API endpoint | `http://localhost:8080` |
| `GRAPH_DB_TIMEOUT` | Request timeout (seconds) | `30` |

**To use in your scripts:**
```python
import os

# Required for graph database
base_url = os.getenv("GRAPH_DB_BASE_URL")  # Auto-provided
timeout = int(os.getenv("GRAPH_DB_TIMEOUT", "30"))  # Auto-provided

# PYTHONPATH is automatically set, just import:
from connectors import GraphConnector
```
---

#### **For API Integration Skills:**
```python
# Real API call with error handling
import requests
import sys
import json

def fetch_weather(city: str, api_key: str):
    url = f"https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": api_key}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python weather_query.py <city> <api_key>")
        sys.exit(1)
    
    city = sys.argv[1]
    api_key = sys.argv[2]
    data = fetch_weather(city, api_key)
    print(json.dumps(data, indent=2))
```
---

#### **Script Requirements Checklist:**

- [ ] Uses **direct imports** (`from connectors import GraphConnector`)
- [ ] **NO** `sys.path.insert()` or `sys.path.append()`
- [ ] Uses correct method names (without `graph_` prefix)
- [ ] Accepts command-line arguments
- [ ] Includes error handling (try-catch blocks)
- [ ] Returns actual data from real sources
- [ ] Has meaningful error messages
- [ ] Exits with proper exit codes (0 = success, 1 = error)
- [ ] Includes docstrings and comments

---

#### **Common Mistakes to Avoid:**

❌ **Mistake 1: Wrong function name**
```python
# WRONG
from connectors import graph_property_filter  # No such function!
results = graph_property_filter(...)
```
✅ **Correct:**
```python
# CORRECT
from connectors import GraphConnector
connector = GraphConnector(...)
results = connector.property_filter(...)
```
---

❌ **Mistake 2: Unnecessary sys.path manipulation**
```python
# WRONG - Don't do this!
import sys
sys.path.insert(0, '/path/to/project')
```
✅ **Correct:**
```python
# CORRECT - Just import directly
from connectors import GraphConnector
```
---

❌ **Mistake 3: Not handling errors**
```python
# WRONG - No error handling
connector = GraphConnector(...)
results = connector.property_filter(...)
print(results)
```
✅ **Correct:**
```python
# CORRECT - With error handling
try:
    connector = GraphConnector(...)
    results = connector.property_filter(...)
    print(json.dumps(results, ensure_ascii=False, indent=2))
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
```
---

**Mistake 4: Using os.popen() instead of subprocess.run()**
```
python
# ❌ WRONG - os.popen() has encoding issues on Windows
import os
result = os.popen("dir").read()
```
✅ **Correct:**
```
python
# ✅ CORRECT - subprocess.run() with explicit encoding
import subprocess
result = subprocess.run(
    ["cmd", "/c", "dir"],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace'  # Replace invalid chars instead of crashing
).stdout
```
**Why?**
- `os.popen()` uses system default encoding (GBK on Windows)
- `subprocess.run()` allows explicit encoding control
- `errors='replace'` prevents UnicodeDecodeError
---

#### **After Creating the Skill:**

1. **Verify** all files are created
2. **Test** the scripts immediately with sample inputs
3. **Report** success or failure to the user
4. **Reload** the skill to make it available
5. **DO NOT** ask the user to manually edit files
6. **DO NOT** leave TODO items for the user

#### **Example: Complete Graph Database Skill Creation**

**User:** "Create a skill to query organizational hierarchy from the graph database"

**Your Response:**

1. **Discover schema:**
   - Call `graph_get_object_types()` → Find "Organ" entity
   - Call `graph_query_examples("Organ", 2)` → Understand structure

2. **Create complete skill:**
   ```
   skills/org-hierarchy/
   ├── SKILL.md
   └── scripts/
       ├── query_org.py       (uses os.getenv for config)
       └── get_hierarchy.py   (uses os.getenv for config)
   ```

3. **Script example (query_org.py):**
   ```python
   import os
   from connectors import GraphConnector
   
   connector = GraphConnector(
       base_url=os.getenv("GRAPH_DB_BASE_URL"),  # ✅ From environment
       timeout=int(os.getenv("GRAPH_DB_TIMEOUT", "30"))
   )
   
   results = connector.property_filter(...)
   ```

4. **Test and report:**
   "✅ Organization hierarchy skill created successfully!
   All scripts use environment-based configuration."

### Step 6: Execution-Time Graph Queries (When Running the Skill)
**When the skill is executed later, it MUST:**

1. **Query actual data from graph database:**
   - Use the entity types and filters defined in the execution flow
   - Fetch real instances based on user's input parameters
   - Example:
     ```python
     # User asks: "Check compliance for task T-2024-001"
     
     # Script queries:
     task_data = graph_property_filter(
         element_class="TransportTask",
         filter_dict={"taskId": "= 'T-2024-001'"},
         get_all_properties=True
     )
     
     # Then get related entities:
     product_uuid = task_data[0]["product_uuid"]
     product_data = graph_property_info(
         element_class="ChemicalProduct",
         element_uuid=product_uuid
     )
     ```

2. **Process the retrieved data:**
   - Apply business logic defined in the skill
   - Validate data against rules
   - Generate insights or reports

3. **Return meaningful results:**
   - Combine graph data with processing results
   - Format output for user consumption

---

## Example Complete Conversation Flow

**User:** "Create a skill to check transport compliance for chemical products"

**You:** "I don't have a skill for transport compliance checking yet. Would you like me to create a 'transport-compliance' skill for this purpose?"

**User:** "Yes"

**You:** "Great! Before I create the skill, do you have any reference documentation? For example:
- Transport compliance regulations
- Chemical product specifications
- Database schema for transport tasks"

**User:** "Yes, I have compliance_rules.md"

**You:** "Perfect! Let me analyze it... [reads file]

I found the following requirements:
- Must check: License validity, product classification, route approval
- Validation rules: [list from doc]

Now let me query the graph database to understand available data..."

[Queries graph database]

**You:** "I've analyzed the graph database and found:
- TransportTask entity (252 instances)
- ChemicalProduct entity (89 instances)
- ComplianceRule entity (45 instances)

Here's the proposed execution flow:

📋 Skill Execution Flow Plan

Skill Name: transport-compliance
Description: Check transport task compliance against regulations for chemical products

📊 Required Graph Entities:
1. TransportTask
   - Properties: taskId, status, productType, route, startDate, endDate
   - Example: taskId='T-2024-001', status='pending'

2. ChemicalProduct  
   - Properties: productId, name, classification, hazardLevel
   - Example: classification='H2SO4', hazardLevel=8

3. ComplianceRule
   - Properties: ruleId, category, requirement, threshold
   - Example: category='license', requirement='valid_permit'

🔄 Execution Steps:
Step 1: Query Transport Task
   - Input: taskId from user
   - Query: graph_property_filter(element_class="TransportTask", filter_dict={"taskId": "= '[user_input]'"})
   - Output: Task details including productType, route

Step 2: Get Product Details
   - Query: graph_property_info(element_class="ChemicalProduct", element_uuid=[from step 1])
   - Output: Product classification, hazard level

Step 3: Get Applicable Compliance Rules
   - Query: graph_property_filter(element_class="ComplianceRule", filter_dict={"category": "CONTAINS 'transport'"})
   - Output: List of rules to check

Step 4: Validate Compliance
   - Process: Check task + product data against each rule
   - Output: Pass/Fail for each rule + overall compliance status

📤 Final Output:
{
  "taskId": "T-2024-001",
  "product": "Sulfuric Acid (H2SO4)",
  "overallCompliance": "PASS/FAIL",
  "checks": [
    {"rule": "License Validity", "status": "PASS/FAIL", "details": "..."},
    {"rule": "Route Approval", "status": "PASS/FAIL", "details": "..."}
  ]
}

Does this execution flow look correct? Should I proceed with creating the skill?"

**User:** "Yes, looks good"

**You:** "Perfect! Creating the skill now..."

[Creates skill]

**You:** "✅ Skill 'transport-compliance' created successfully!

Based on our execution flow, you should now:
1. Edit SKILL.md with the entity documentation
2. Create check_compliance.py script following the flow above
3. Add compliance_rules.md to references/
4. Test with: python check_compliance.py T-2024-001"