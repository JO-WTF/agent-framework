---
name: python_debug
description: Python code debugging and execution guidelines.
tags: [python, tool_error]
---

# Python Debugging SOP

When encountering Python errors or writing code, you MUST:
1. **Analyze Tracebacks**: Closely inspect Python runtime stack trace errors to identify syntax, type, or name mismatches.
2. **Validate Code**: Always test local edits by running test files using the command line (e.g. pytest) rather than assuming code runs cleanly.
3. **Handle Dependencies**: If a module is missing, suggest installation and seek confirmation before proceeding.
