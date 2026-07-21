"""
CC Usage — Query CC Switch proxy request logs for per-turn token usage.

Reads from ~/.cc-switch/cc-switch.db proxy_request_logs table
and displays per-turn input/output tokens, latency, and estimates.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
BEIJING_TZ = timezone(timedelta(hours=8))


def find_current_session_id():
    """Auto-detect the latest active session from the JSONL files."""
    project_dir = Path.home() / ".claude" / "projects"
    if not project_dir.exists():
        return None
    # Also check the common project directory patterns
    candidates = []
    for pattern in ["C--Users-SI-Agent-AgentProject", "c--Users-SI-Agent-AgentProject"]:
        d = project_dir / pattern
        if d.exists():
            for f in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.stat().st_size > 1000:
                    candidates.append(f)
            break
    if not candidates:
        # broader search
        for d in project_dir.iterdir():
            if d.is_dir():
                for f in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
                    if f.stat().st_size > 1000:
                        candidates.append(f)
    if not candidates:
        return None
    # Pick the most recently modified JSONL
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest.stem


def fmt_ts(epoch):
    if not epoch:
        return "N/A"
    return datetime.fromtimestamp(epoch, tz=BEIJING_TZ).strftime("%H:%M:%S")


def fmt_num(n):
    if n is None or n == 0:
        return "0"
    if n >= 1_000_000:
        return f"{n/1e6:.2f}M"
    if n >= 1_000:
        return f"{n/1e3:.1f}K"
    return str(n)


def query_logs(n=20, session_id=None, model_filter=None):
    db = DB_PATH
    if not db.exists():
        print(f"Error: CC Switch database not found at {db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    where_clauses = []
    params = []

    if session_id:
        where_clauses.append("session_id = ?")
        params.append(session_id)

    if model_filter:
        mf = model_filter.lower()
        if mf == "opus":
            where_clauses.append("(request_model LIKE '%opus%' OR model LIKE '%opus%')")
        elif mf == "haiku":
            where_clauses.append("(request_model LIKE '%haiku%' OR model LIKE '%haiku%')")
        elif mf == "sonnet":
            where_clauses.append("(request_model LIKE '%sonnet%' OR model LIKE '%sonnet%')")

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Count total
    count_row = conn.execute(f"SELECT COUNT(*) FROM proxy_request_logs{where_sql}", params).fetchone()
    total = count_row[0]

    query = f"""
        SELECT
            created_at,
            model,
            request_model,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
            latency_ms,
            first_token_ms,
            duration_ms,
            status_code,
            session_id
        FROM proxy_request_logs
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
    """
    params.append(n)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Reverse to chronological order
    rows = list(reversed(rows))
    return rows, total


def query_latest_per_model(session_id=None):
    """Get the most recent record for each of: Sonnet, Opus, Haiku."""
    db = DB_PATH
    if not db.exists():
        print(f"Error: CC Switch database not found at {db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    where_sql = ""
    params = []
    if session_id:
        where_sql = "WHERE session_id = ?"
        params.append(session_id)

    # Get latest record per model family
    query = f"""
        SELECT
            created_at,
            model,
            request_model,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
            latency_ms,
            first_token_ms
        FROM proxy_request_logs p
        INNER JOIN (
            SELECT MAX(created_at) AS latest_at
            FROM proxy_request_logs
            {where_sql}
            GROUP BY CASE
                WHEN request_model LIKE '%sonnet%' OR model LIKE '%sonnet%' THEN 'sonnet'
                WHEN request_model LIKE '%opus%' OR model LIKE '%opus%' THEN 'opus'
                WHEN request_model LIKE '%haiku%' OR model LIKE '%haiku%' THEN 'haiku'
                ELSE request_model
            END
        ) latest
        ON p.created_at = latest.latest_at
        {where_sql}
        ORDER BY p.created_at DESC
    """
    rows = conn.execute(query, params + params).fetchall()
    conn.close()
    return list(reversed(rows))


CONTEXT_LIMIT = 262_144  # Default context window limit


def print_usage_bar(rows, limit: int = CONTEXT_LIMIT) -> None:
    """Print a context usage bar for each model's latest turn."""
    for r in rows:
        model = r["request_model"] or r["model"] or "?"
        if "sonnet" in model.lower():
            model_short = "Sonnet"
        elif "opus" in model.lower():
            model_short = "Opus"
        elif "haiku" in model.lower():
            model_short = "Haiku"
        else:
            model_short = model[:8]

        inp = r["input_tokens"] or 0
        outp = r["output_tokens"] or 0
        input_pct = inp / limit
        output_pct = outp / limit

        bar_width = 30
        filled_in = round(input_pct * bar_width)
        filled_out = round(output_pct * bar_width)

        input_bar = "█" * filled_in + "░" * (bar_width - filled_in)
        output_bar = "█" * filled_out + "░" * (bar_width - filled_out)

        input_color = "\033[92m" if input_pct < 0.6 else ("\033[93m" if input_pct < 0.8 else "\033[91m")
        output_color = "\033[92m" if output_pct < 0.6 else ("\033[93m" if output_pct < 0.8 else "\033[91m")
        reset = "\033[0m"

        print(f"  {model_short:8s} {input_color}In [{input_bar}] {input_pct*100:5.1f}% ({fmt_num(inp)}){reset}")
        print(f"{' ' * 10} {output_color}Out[{output_bar}] {output_pct*100:5.1f}% ({fmt_num(outp)}){reset}")


def print_latest(rows, session_id=None):
    """Print the most recent token usage per model family."""
    if not rows:
        print("No records found.")
        return

    # Find max input/output across all models
    max_input = max((r["input_tokens"] or 0) for r in rows)
    max_output = max((r["output_tokens"] or 0) for r in rows)

    print("=== Context Usage Bar ===")
    print_usage_bar(rows)
    print()
    print("=== Latest Token Usage per Model ===\n")

    headers = ["Model", "Time", "Input", "Output", "CacheR", "CacheC", "Latency"]
    data_lines = []

    for r in rows:
        ts = fmt_ts(r["created_at"])
        lat = f"{(r['latency_ms'] or 0) / 1000:.1f}s"
        model = r["request_model"] or r["model"] or "?"

        # Short model name
        model_short = model
        if "sonnet" in model.lower():
            model_short = "Sonnet" + model.split("sonnet")[1].split("-")[0] if "-" in model else "Sonnet"
        elif "opus" in model.lower():
            model_short = "Opus" + model.split("opus")[1].split("-")[0] if "-" in model else "Opus"
        elif "haiku" in model.lower():
            model_short = "Haiku" + model.split("haiku")[1].split("-")[0] if "-" in model else "Haiku"

        inp = r["input_tokens"] or 0
        outp = r["output_tokens"] or 0
        cr = r["cache_read_tokens"] or 0
        cc = r["cache_creation_tokens"] or 0

        data_lines.append({
            "Model": model_short,
            "Time": ts,
            "Input": fmt_num(inp) + f" ({inp:,})",
            "Output": fmt_num(outp) + f" ({outp:,})",
            "CacheR": fmt_num(cr),
            "CacheC": fmt_num(cc),
            "Latency": lat,
        })

    # Calculate column widths
    widths = {h: len(h) for h in headers}
    for d in data_lines:
        for h in headers:
            widths[h] = max(widths[h], len(d[h]))

    fmt_str = " | ".join(f"{{:<{widths[h]}}}" for h in headers)
    sep = "|".join(f" {'-' * widths[h]} " for h in headers)

    print(fmt_str.format(*headers))
    print(sep)
    for d in data_lines:
        print(fmt_str.format(*[d[h] for h in headers]))

    if session_id:
        print(f"\nSession: {session_id}")


def print_table(rows, show_estimation=True):
    if not rows:
        print("No records found.")
        return

    headers = ["Turn", "Time", "Input", "Output", "CacheR", "CacheC", "Latency", "FirstTk", "Model"]
    data_lines = []

    total_in = 0
    total_out = 0
    total_latency = 0
    opus_turns = []
    haiku_turns = []

    for i, r in enumerate(rows):
        ts = fmt_ts(r["created_at"])
        lat = f"{(r['latency_ms'] or 0) / 1000:.1f}s"
        ft = f"{(r['first_token_ms'] or 0) / 1000:.1f}s"
        model = r["request_model"] or r["model"] or "?"
        marker = " [sub]" if "haiku" in model.lower() else ""

        data_lines.append({
            "Turn": f"T{i + 1}",
            "Time": ts,
            "Input": r["input_tokens"],
            "Output": r["output_tokens"],
            "CacheR": r["cache_read_tokens"] or 0,
            "CacheC": r["cache_creation_tokens"] or 0,
            "Latency": lat,
            "FirstTk": ft,
            "Model": model + marker,
            "raw_model": model,
        })
        total_in += r["input_tokens"]
        total_out += r["output_tokens"]
        total_latency += r["latency_ms"] or 0

        if "haiku" in model.lower():
            haiku_turns.append(r)
        else:
            opus_turns.append(r)

    # Calculate column widths
    widths = {h: len(h) for h in headers}
    for d in data_lines:
        for h in headers:
            val = d[h] if h != "Input" and h != "Output" and h != "CacheR" and h != "CacheC" else str(d[h])
            widths[h] = max(widths[h], len(val))

    widths["Model"] = min(widths["Model"], 40)

    fmt_str = " | ".join(f"{{:<{widths[h]}}}" for h in headers)
    sep = "|".join(f" {'-' * widths[h]} " for h in headers)

    print(fmt_str.format(*headers))
    print(sep)
    for d in data_lines:
        model_display = (d["Model"] or "?")[:widths["Model"]]
        print(fmt_str.format(
            d["Turn"], d["Time"],
            d["Input"], d["Output"],
            d["CacheR"], d["CacheC"],
            d["Latency"], d["FirstTk"],
            model_display,
        ))

    # Summary
    print()
    print("=== Summary ===")
    print(f"Total turns      : {len(rows)}")
    print(f"Opus turns       : {len(opus_turns)} (input={fmt_num(sum(r['input_tokens'] for r in opus_turns))}, output={fmt_num(sum(r['output_tokens'] for r in opus_turns))})")
    if haiku_turns:
        print(f"Haiku turns      : {len(haiku_turns)} (input={fmt_num(sum(r['input_tokens'] for r in haiku_turns))}, output={fmt_num(sum(r['output_tokens'] for r in haiku_turns))})")
    print(f"Grand total input:  {fmt_num(total_in)} ({total_in:,})")
    print(f"Grand total output: {fmt_num(total_out)} ({total_out:,})")
    if len(rows) > 0:
        print(f"Avg latency      : {(total_latency / len(rows) / 1000):.1f}s")

    # Estimation
    if show_estimation:
        # Filter non-zero opus turns for estimation
        valid_opus = [r for r in opus_turns if r["input_tokens"] > 0]
        if len(valid_opus) > 2:
            print()
            print("=== Current Turn Estimation ===")
            # Calculate recent delta from opus turns only
            deltas = []
            for i in range(1, len(valid_opus)):
                d = valid_opus[i]["input_tokens"] - valid_opus[i - 1]["input_tokens"]
                deltas.append(d)

            # Recent 5 turns delta
            recent_deltas = deltas[-5:] if len(deltas) >= 5 else deltas
            avg_delta = sum(recent_deltas) / len(recent_deltas)

            last_input = valid_opus[-1]["input_tokens"]
            est_next = last_input + int(avg_delta)

            # Recent output average
            recent_out = [r["output_tokens"] for r in valid_opus[-5:]]
            avg_out = sum(recent_out) / len(recent_out)

            print(f"Last Opus input:  {last_input:,}")
            print(f"Avg context delta: +{avg_delta:.0f} tokens/turn")
            print(f"Est. next turn input: ~{est_next:,} ({est_next / 1000:.1f}K)")
            print(f"Est. next turn output: ~{avg_out:.0f} (recent 5-turn avg)")


def main():
    parser = argparse.ArgumentParser(description="Query CC Switch proxy token usage")
    parser.add_argument("--n", type=int, default=2,
                        help="Number of recent records to show (default: 2)")
    parser.add_argument("--session", type=str, default=None,
                        help="Session ID (auto-detects current session if omitted)")
    parser.add_argument("--model", type=str, default=None,
                        choices=["opus", "sonnet", "haiku"],
                        help="Filter by model family")
    parser.add_argument("--latest", action="store_true",
                        help="Show only the most recent record per model (Sonnet, Opus, Haiku)")
    args = parser.parse_args()

    session_id = args.session or find_current_session_id()

    # If --model is specified, show filtered table view
    if args.model:
        if session_id and not args.session:
            print(f"Auto-detected session: {session_id}\n")
        elif not session_id:
            print("Warning: Could not auto-detect session\n", file=sys.stderr)
        rows, total = query_logs(n=args.n, session_id=session_id, model_filter=args.model)
        if session_id:
            print(f"Session: {session_id}")
            print(f"Showing: {min(len(rows), total)} of {total} records\n")
        print_table(rows, show_estimation=False)
        return

    # Default: show latest per model
    rows = query_latest_per_model(session_id=session_id)
    if session_id and not args.session:
        print(f"Auto-detected session: {session_id}\n")
    print_latest(rows, session_id=session_id)


if __name__ == "__main__":
    main()
