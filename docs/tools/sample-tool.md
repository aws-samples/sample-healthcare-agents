# Sample Tool

Example Lambda-based Gateway target demonstrating the implementation pattern.

## Tool

**text_analysis_tool** - Analyzes text and returns word count and character frequency.

## Purpose

Reference implementation showing:
- Lambda target pattern for AgentCore Gateway
- Parsing tool name from context
- MCP response format
- Error handling

## Implementation

**Location:** `gateway/tools/sample_tool/sample_tool_lambda.py`

Key pattern:
```python
def handler(event, context):
    # Get tool name from context
    tool_name = context.client_context.custom['bedrockAgentCoreToolName']

    # Strip target prefix
    if '___' in tool_name:
        tool_name = tool_name.split('___')[-1]

    # Get arguments from event
    text = event.get('text', '')
    n = event.get('n', 5)

    # Return MCP format
    return {
        'content': [{
            'type': 'text',
            'text': result_string
        }]
    }
```

## Usage

```python
response = gateway.call_tool(
    "sample-tool-target___text_analysis_tool",
    {"text": "Hello world", "n": 3}
)
```

## Related

- [Gateway Architecture](../architecture/GATEWAY.md) - Full Lambda target pattern
- [Tools Overview](overview.md)
