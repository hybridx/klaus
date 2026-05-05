# Tool: text_transform

Transform text by applying common string operations.

## Parameters
- text (string, required): The input text to transform
- operation (string, required): The operation: "upper", "lower", "title", "reverse", "word_count", "char_count", "slug"

## Implementation
```python
import re

async def run(text: str, operation: str) -> str:
    ops = {
        "upper": lambda t: t.upper(),
        "lower": lambda t: t.lower(),
        "title": lambda t: t.title(),
        "reverse": lambda t: t[::-1],
        "word_count": lambda t: str(len(t.split())),
        "char_count": lambda t: str(len(t)),
        "slug": lambda t: re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-"),
    }
    fn = ops.get(operation)
    if fn is None:
        return f"Unknown operation: {operation}. Available: {', '.join(ops.keys())}"
    return fn(text)
```
