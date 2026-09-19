import inspect
from typing import Callable, Any

class ToolRegistry:
    def __init__(self):
        self._tools = {}
        
    def register(self, args_schema=None):
        """
        Decorator to register a function as a tool.
        Optionally takes a Pydantic BaseModel as args_schema for parameter descriptions.
        """
        def decorator(func: Callable):
            self._tools[func.__name__] = {
                "func": func,
                "args_schema": args_schema
            }
            return func
            
        # Support both @registry.register and @registry.register(args_schema=...)
        if callable(args_schema) and not (isinstance(args_schema, type) and hasattr(args_schema, 'model_json_schema')):
            func = args_schema
            args_schema = None
            self._tools[func.__name__] = {
                "func": func,
                "args_schema": None
            }
            return func
            
        return decorator
        
    def get_schemas(self):
        """Generates OpenAI-compatible tool schemas for all registered tools."""
        schemas = []
        for name, tool_data in self._tools.items():
            func = tool_data["func"]
            args_schema = tool_data["args_schema"]
            
            # Extract description from function docstring
            doc = inspect.getdoc(func) or ""
            description = doc.split("\n\n")[0] if doc else "No description provided."
            
            # Generate parameters from Pydantic schema if provided
            parameters = {"type": "object", "properties": {}}
            if args_schema:
                model_schema = args_schema.model_json_schema()
                parameters["properties"] = model_schema.get("properties", {})
                if "required" in model_schema:
                    parameters["required"] = model_schema["required"]
            else:
                # If no schema provided, we assume no arguments for simplicity
                pass
                
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            })
            
        return schemas
        
    def call_tool(self, name: str, args: dict) -> Any:
        """Calls a registered tool by name with the given arguments."""
        if name not in self._tools:
            return f"Error: Unknown function {name}"
            
        func = self._tools[name]["func"]
        try:
            return func(**args)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

# Global registry instance
registry = ToolRegistry()
