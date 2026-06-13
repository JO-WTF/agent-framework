import re
import json
from typing import Any
from app.tools.storage import read_tool_result_for_current_session
from app.logging_config import logger

REF_PATTERN = re.compile(r"^{{ref:(tool-[a-zA-Z0-9]+)(?:#(.*))?}}$")

def _extract_by_path(obj: Any, path: str) -> Any:
    if not path:
        return obj
    
    # Simple path splitting by /
    parts = [p for p in path.split('/') if p]
    current = obj
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                raise KeyError(f"Path part '{part}' not found in dict.")
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except ValueError:
                raise ValueError(f"Path part '{part}' is not a valid list index.")
            except IndexError:
                raise IndexError(f"List index '{part}' out of range.")
        else:
            raise TypeError(f"Cannot extract path part '{part}' from type {type(current).__name__}.")
    return current

def _resolve_string(value: str) -> Any:
    match = REF_PATTERN.match(value.strip())
    if not match:
        return value
    
    ref_id = match.group(1)
    path = match.group(2)
    
    # Read the tool result bypassing standard length limits to get full data
    try:
        record = read_tool_result_for_current_session(ref_id=ref_id, offset=0, limit=10000000)
    except Exception as e:
        raise ValueError(f"Failed to read reference '{ref_id}': {str(e)}")
    
    content = record.get("content", "")
    
    # Attempt to parse as JSON
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        if path:
            raise ValueError(f"Cannot extract path '#{path}' from reference '{ref_id}' because its content is not valid JSON.")
        return content
    
    # Extract path if provided
    try:
        return _extract_by_path(obj, path)
    except Exception as e:
        raise ValueError(f"Failed to extract path '#{path}' from reference '{ref_id}': {str(e)}")

def resolve_tool_args(args: Any) -> Any:
    """
    Recursively traverse arguments and resolve {{ref:tool-xxxx#path}} strings.
    """
    if isinstance(args, str):
        return _resolve_string(args)
    elif isinstance(args, dict):
        return {k: resolve_tool_args(v) for k, v in args.items()}
    elif isinstance(args, list):
        return [resolve_tool_args(v) for v in args]
    else:
        return args
