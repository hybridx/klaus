# Tool: calculator

Evaluate a mathematical expression and return the result. Supports basic arithmetic, exponents, and common math functions.

## Parameters
- expression (string, required): The mathematical expression to evaluate (e.g. "2 + 3 * 4")

## Implementation
```python
import math

async def run(expression: str) -> str:
    allowed = {
        "abs": abs, "round": round, "min": min, "max": max,
        "pow": pow, "sqrt": math.sqrt, "log": math.log,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "pi": math.pi, "e": math.e,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)
    except Exception as exc:
        return f"Error: {exc}"
```
