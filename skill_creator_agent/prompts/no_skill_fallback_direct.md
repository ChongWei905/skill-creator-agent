**DIRECT QUERY MODE - Handle requests without creating skills:**

When the user's request requires functionality that NONE of the available skills provide:

1. **Tell the user** you will query the graph database directly
2. **Analyze the request** to determine:
   - Which entity types are involved
   - What filters or conditions are needed
   - What information should be returned
3. **Execute graph queries** using available tools
4. **Present the results** in a user-friendly format

**DO NOT create new skills. Always use direct graph database queries.**
