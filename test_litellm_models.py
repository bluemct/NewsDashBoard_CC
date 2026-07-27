#!/usr/bin/env python
"""Test calling DeepSeek via LiteLLM - try multiple model names."""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from litellm import completion

API_BASE = "http://61.49.53.5:30001/v1"
API_KEY = "deepSeek-v3.1"

# Try different model name variants
model_names = [
    "deepseek-v3.1",
    "deepseek-v3.2",
    "deepSeek-v3.1",
    "deepSeek-v3.2",
    "DeepSeek-V3",
    "DeepSeek-V3.1",
    "DeepSeek-V2",
]

messages = [
    {"role": "user", "content": "你好，请回复hello"}
]

for model in model_names:
    print(f"\nTrying model: {model}")
    try:
        resp = completion(
            model=f"openai/{model}",
            api_base=API_BASE,
            api_key=API_KEY,
            messages=messages,
            timeout=15
        )
        if hasattr(resp, 'choices'):
            print(f"  SUCCESS! Content: {resp.choices[0].message.content[:100]}")
            break
        else:
            print(f"  Got response but no choices")
    except Exception as e:
        err = str(e)
        if "does not exist" in err or "not found" in err.lower():
            print(f"  Model not found")
        elif "token" in err.lower() or "auth" in err.lower():
            print(f"  Auth failed: {err[:80]}")
        else:
            print(f"  Error: {err[:100]}")
