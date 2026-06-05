# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a beginner-level Python learning project. It contains simple standalone scripts with no external dependencies, no virtual environment, and no build system.

## Files

- `runoob-claude-demo/main.py` — Core demo script. Defines an `add()` function with type checking, logging, and inline self-tests (asserts + try/except).
- `test.py` — Simple `hello_world()` print script.

## Running Code

No dependencies to install. Run scripts directly with Python 3:

```bash
python3 runoob-claude-demo/main.py
python3 test.py
```

## Custom Skills

- `/watch-file` — Monitors `runoob-claude-demo/main.py` for file changes via MD5 checksum comparison.
