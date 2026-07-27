#!/usr/bin/env python
"""Test calling internal model via LiteLLM."""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from litellm import completion

def test_litellm():
    print("Testing LiteLLM completion...")
    try:
        resp = completion(
            model="openai/WanWu/MiniMax-M3",
            api_base="http://61.49.53.5:30001/v1",
            api_key="deepSeek-v3.1",
            messages=[
                {"role": "system", "content": "您好！我是世纪互联AI人工智能助手"},
                {"role": "user", "content": "你好，请简单介绍一下你自己。"}
            ],
            timeout=30
        )
        print(f"Success!")
        print(f"Content: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_litellm()
