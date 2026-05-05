# Tool: date_time

Get the current date, time, or perform date calculations. Returns formatted date/time strings.

## Parameters
- action (string, required): One of "now", "date", "time", "weekday", or "diff"
- format (string): strftime format string (default: "%Y-%m-%d %H:%M:%S")
- date_str (string): A date string for calculations (ISO format)

## Implementation
```python
from datetime import datetime, timedelta

async def run(action: str, format: str = "%Y-%m-%d %H:%M:%S", date_str: str = "") -> str:
    now = datetime.now()
    if action == "now":
        return now.strftime(format)
    elif action == "date":
        return now.strftime("%Y-%m-%d")
    elif action == "time":
        return now.strftime("%H:%M:%S")
    elif action == "weekday":
        return now.strftime("%A")
    elif action == "diff" and date_str:
        try:
            target = datetime.fromisoformat(date_str)
            diff = target - now
            return f"{diff.days} days, {diff.seconds // 3600} hours"
        except ValueError:
            return "Invalid date format. Use ISO format (YYYY-MM-DD)"
    return f"Unknown action: {action}"
```
