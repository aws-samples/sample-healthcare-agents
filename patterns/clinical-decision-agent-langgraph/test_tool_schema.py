#!/usr/bin/env python3
"""Check the tool schema"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

os.environ['STACK_NAME'] = 'healthcare-agents-stack'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_REGION'] = 'us-east-1'

from clinical_decision_agent import create_epic_fhir_tools
import json

# Create Epic tools
callback_url = "https://main.***REMOVED_AMPLIFY_APP_ID***.amplifyapp.com/oauth/callback"
epic_tools = create_epic_fhir_tools(callback_url)

print("Epic FHIR Tools:\n")
for tool in epic_tools:
    print(f"Tool: {tool.name}")
    print(f"Description: {tool.description}")
    if hasattr(tool, 'args_schema') and tool.args_schema:
        schema = tool.args_schema.schema()
        print(f"Schema: {json.dumps(schema, indent=2)}")
    else:
        print("No args_schema")
    print("-" * 80)
