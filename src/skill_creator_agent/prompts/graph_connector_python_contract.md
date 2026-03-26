## GraphConnector Python Contract

When writing Python skill scripts, the current connector API is:

```python
from connectors import GraphConnector

connector = GraphConnector(
    base_url=os.getenv("GRAPH_DB_BASE_URL"),
    timeout=int(os.getenv("GRAPH_DB_TIMEOUT", "30")),
)
```

Use GraphConnector instance methods directly:

```python
results = connector.property_filter(
    element_class="Organ",
    element_type="NODE",
    filter_dict={"name": "CONTAINS '蛇口'"},
    get_all_properties=True,
)
```

### Required method signatures

- `connector.property_filter(element_class, element_type="NODE", filter_dict={...}, get_all_properties=True|False)`
- `connector.property_info_search(element_class, element_type="NODE", element_uuid="...")`
- `connector.count_search(element_class, element_type="NODE", filter_dict={...})`
- `connector.query_examples(entity_type, limit=5, filter_dict={...})`

### Filter syntax

`filter_dict` values must be plain strings, not nested dictionaries:

- `= '0400000012'`
- `> 0`
- `< 100`
- `CONTAINS '蛇口'`
- `STARTS WITH '04'`
- `ENDS WITH '30'`
- `>= '20240101'`
- `<= '20241231'`

### Returned data shape

When `get_all_properties=True`, the return value is a list of flat dictionaries:

```python
row.get("name")
row.get("organ_code")
row.get("ORGAN_CODE")
row.get("DATA_DATE")
row.get("Value")
row.get("uuid")
```

### Do not generate these incorrect patterns

```python
# WRONG: unsupported keyword names
connector.property_filter(entity="Organ", property_filter={...})

# WRONG: nested operator dictionaries
{"name": {"contains": "蛇口"}}
{"ORGAN_CODE": {"equals": "0400000012"}}
{"DATA_DATE": {"between": ["20240101", "20241231"]}}

# WRONG: unsupported BETWEEN/AND syntax in one filter expression
{"DATA_DATE": "BETWEEN '20240101' AND '20241231'"}

# WRONG: prefixed helper function names
graph_property_filter(...)
graph_property_info(...)
```
