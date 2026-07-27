"""
Usage — Query recent Claude Code session token usage.

Reads from the claude-usage SQLite database (~/.claude/usage.db) and
displays recent sessions with token counts.

Usage:
    python usage.py [--n N] [--model MODEL] [--project PROJECT]
"""
import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Force UTF-8 stdout for Chinese topic names on Windows
if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB_PATH = Path.home() / ".claude" / "usage.db"


def fmt(n):
    if n is None or n == 0:
        return "0"
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.2f}M"
    if n >= 1e3:
        return f"{n/1e3:.1f}K"
    return str(n)


def query_sessions(n=10, model=None, project=None):
    db = Path(DB_PATH)
    if not db.exists():
        print(f"Error: Database not found at {db}", file=sys.stderr)
        print("Run: python cli.py scan", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row

    where_clauses = []
    params = []
    if model:
        where_clauses.append("s.model LIKE ?")
        params.append(f"%{model}%")
    if project:
        where_clauses.append("s.project_name LIKE ?")
        params.append(f"%{project}%")

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = f"""
        SELECT
            s.session_id,
            s.project_name,
            s.topic,
            s.model,
            s.turn_count,
            s.total_input_tokens,
            s.total_output_tokens,
            s.total_cache_read,
            s.total_cache_creation,
            s.last_timestamp,
            s.first_timestamp,
            s.git_branch
        FROM sessions s
        {where_sql}
        ORDER BY s.last_timestamp DESC
        LIMIT ?
    """
    params.append(n)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return rows


def print_table(rows):
    if not rows:
        print("No sessions found.")
        return

    # Column headers
    headers = ["Last Active", "Model", "Project", "Topic", "Turns", "Input", "Output"]

    # Calculate column widths
    widths = [len(h) for h in headers]
    for r in rows:
        last_ts = (r["last_timestamp"] or "")[:16].replace("T", " ")
        widths[0] = max(widths[0], len(last_ts))
        widths[1] = max(widths[1], len(r["model"] or "?"))
        widths[2] = max(widths[2], len(r["project_name"] or "?"))
        topic = (r["topic"] or "")[:40]
        if len(r["topic"] or "") > 40:
            topic += "..."
        widths[3] = max(widths[3], len(topic))
        widths[4] = max(widths[4], len(str(r["turn_count"] or 0)))
        widths[5] = max(widths[5], len(fmt(r["total_input_tokens"])))
        widths[6] = max(widths[6], len(fmt(r["total_output_tokens"])))

    # Cap Topic width
    widths[3] = min(widths[3], 50)

    # Build format string
    fmt_str = "  ".join(f"{{:<{w}}}" for w in widths)

    # Print header
    header_line = fmt_str.format(*headers)
    print(header_line)
    print("  ".join("-" * w for w in widths))

    # Print rows
    total_turns = 0
    total_input = 0
    total_output = 0

    for r in rows:
        last_ts = (r["last_timestamp"] or "")[:16].replace("T", " ")
        model_name = r["model"] or "?"
        project_name = r["project_name"] or "?"
        topic = (r["topic"] or "")[:40]
        if len(r["topic"] or "") > 40:
            topic += "..."

        turns = r["turn_count"] or 0
        inp = r["total_input_tokens"] or 0
        out = r["total_output_tokens"] or 0

        total_turns += turns
        total_input += inp
        total_output += out

        print(fmt_str.format(
            last_ts,
            model_name,
            project_name[:widths[2]],
            topic,
            turns,
            fmt(inp),
            fmt(out),
        ))

    # Print totals
    print("  ".join("-" * w for w in widths))
    print(fmt_str.format(
        f"TOTAL ({len(rows)} sessions)", "", "", "",
        total_turns,
        fmt(total_input),
        fmt(total_output),
    ))


def main():
    parser = argparse.ArgumentParser(description="Query Claude Code token usage")
    parser.add_argument("--n", type=int, default=10,
                        help="Number of recent sessions to show (default: 10)")
    parser.add_argument("--model", type=str, default=None,
                        help="Filter by model name (substring match)")
    parser.add_argument("--project", type=str, default=None,
                        help="Filter by project name (substring match)")
    args = parser.parse_args()

    rows = query_sessions(n=args.n, model=args.model, project=args.project)
    print_table(rows)


if __name__ == "__main__":
    main()
