#!/usr/bin/env python
"""Test calling internal DeepSeek model via OpenAI-compatible API."""

import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# TODO: 填入实际的模型 Key
API_KEY = "deepSeek-v3.1"

BASE_URL = "https://wan.vnet.com/v1/chat/completions"
MODEL_NAME = "deepSeek-v3.1"

import requests

def test_model():
    url = BASE_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "您好！我是世纪互联DeepSeek-v3AI人工智能助手，企业内部服务器加持，为您提供安全、高效的服务。"},
            {"role": "user", "content": "你好，请简单介绍一下你自己。"}
        ],
        "max_tokens": 200,
        "temperature": 0.7
    }

    print(f"URL: {url}")
    print(f"Model: {MODEL_NAME}")
    print(f"API Key: {API_KEY[:4]}...{API_KEY[-4:]}" if len(API_KEY) > 8 else f"API Key: {API_KEY}")
    print("-" * 50)

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        print(f"Response:\n{resp.text}")
    except requests.exceptions.ConnectionError as e:
        print(f"连接失败: {e}")
        print("请确认内网地址 61.49.53.5:30002 可达")
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    test_model()
