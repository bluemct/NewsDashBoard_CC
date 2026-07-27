"""
Test: EWS 过滤 + LLM 分析 (Stage 1 + Stage 2)

不依赖 GUI，命令行直接跑：
  1. 连接 EWS → 扫描 EDM 文件夹
  2. 应用 FilterEngine 过滤规则
  3. 对通过过滤的邮件调用 LLM 分析

用法:
    python test_filter_and_llm.py
"""
import json
import os
import sys
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

# 确保 Windows GBK 终端支持 Unicode 输出
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ---- Load config ----
CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_config.json")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

ews_config = config["ews"]
FILTER_RULES = config.get("filter_rules", {})

LLM_CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_llm_config.json")
llm_defaults = {
    "model": "openai/WanWu/MiniMax-M3",
    "api_base": "http://61.49.53.5:30001/v1",
    "api_key": "deepSeek-v3.1",
    "timeout": 30,
}
if os.path.isfile(LLM_CONFIG_FILE):
    try:
        with open(LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
            llm_defaults.update(json.load(f))
    except (json.JSONDecodeError, IOError):
        pass

# ---- Import from edm_agent ----
from edm_agent import EWSClient, FilterEngine, EmailAnalyzer, SeenTracker

# ===================================================================
# Stage 1: EWS 扫描 + 过滤
# ===================================================================

def test_ews_and_filter():
    print("=" * 60)
    print("STAGE 1: EWS 扫描 + 过滤规则")
    print("=" * 60)

    # --- FilterEngine ---
    filter_engine = FilterEngine(FILTER_RULES)
    print(f"\n过滤规则: {filter_engine.describe()}")
    print(f"  发件人白名单: {filter_engine._sender_list}")
    print(f"  主题关键字:   {filter_engine._subject_kws}")
    print(f"  正文关键字:   {filter_engine._body_kws}")

    # --- EWS 连接 ---
    print(f"\n连接 EWS: {ews_config['url']}")
    print(f"邮箱: {ews_config['mailbox']}")

    client = EWSClient(
        url=ews_config["url"],
        domain_user=ews_config["domain_user"],
        password=ews_config["password"],
        mailbox=ews_config["mailbox"],
    )

    folder_name = ews_config.get("folder_name", "EDM")
    folder_id = client.find_folder(folder_name)
    if not folder_id:
        print(f"FAIL: 找不到文件夹 '{folder_name}'")
        return []

    print(f"OK: 找到文件夹 '{folder_name}' (id={folder_id[:40]}...)")

    # --- 扫描新邮件 ---
    from datetime import datetime, timedelta
    # 扩大扫描窗口到 24 小时，用于调试（正式运行时用 SeenTracker 的 2 小时）
    since = datetime.now() - timedelta(hours=36)
    print(f"\n扫描时间范围: {since.isoformat()} 以来的邮件 (36h 调试窗口)")

    items = client.find_items_since(folder_id, since, max_items=50)
    print(f"EWS 返回: {len(items)} 封有附件的邮件")

    # --- 过滤 ---
    passed = []
    for item in items:
        sender = item.get("sender", "")
        subject = item.get("subject", "")
        item_id = item.get("item_id", "")

        # Layer 1: quick filter (sender + subject, no body)
        if not filter_engine.matches(sender, subject):
            print(f"  [FILTER SKIP] {sender} | {subject[:60]}")
            continue

        print(f"  [FILTER OK]   {sender} | {subject[:60]}")
        passed.append(item)

    print(f"\n过滤结果: {len(passed)}/{len(items)} 封邮件通过")
    return passed


# ===================================================================
# Stage 2: LLM 分析
# ===================================================================

def test_llm_analysis(passed_items):
    print("\n" + "=" * 60)
    print("STAGE 2: LLM 邮件分析")
    print("=" * 60)
    print(f"LLM 模型: {llm_defaults['model']}")
    print(f"API Base: {llm_defaults['api_base']}")
    print(f"Timeout:  {llm_defaults.get('timeout', 30)}s")

    if not passed_items:
        print("\n没有通过过滤的邮件，跳过 LLM 分析")
        return

    # Re-import EWSClient for get_item_body
    client = EWSClient(
        url=ews_config["url"],
        domain_user=ews_config["domain_user"],
        password=ews_config["password"],
        mailbox=ews_config["mailbox"],
    )
    analyzer = EmailAnalyzer()

    results = []
    for i, item in enumerate(passed_items, 1):
        item_id = item.get("item_id", "")
        sender = item.get("sender", "")
        subject = item.get("subject", "")

        print(f"\n{'─' * 50}")
        print(f"[{i}/{len(passed_items)}] 分析: {subject[:60]}")
        print(f"    发件人: {sender}")

        # --- 获取正文 ---
        body_info = client.get_item_body(item_id)
        body_text = body_info.get("body", "")
        body_subject = body_info.get("subject", subject)

        # Layer 2: filter with body — 使用外层主题 + 正文
        # 注意: body_subject 是内层邮件主题（转发场景下不含 FW 前缀）
        # 外层主题已在 Layer 1 通过，这里只追加正文检查
        if body_text and not FilterEngine(FILTER_RULES).matches(sender, subject, body_text):
            # 正文非空但三层都不匹配 → 跳过
            if not filter_engine.matches(sender, subject):
                print(f"    [FILTER SKIP - body check]")
                results.append({"item_id": item_id, "action": "filtered", "subject": body_subject, "confidence": 0, "reason": "body filter skip", "sn": ""})
                continue

        # 正文为空时，Layer 1 已通过，放行
        print(f"    正文长度: {len(body_text)} 字符")
        if body_text:
            print(f"    正文预览: {body_text[:120]}...")
        print(f"    内层主题: {body_subject[:60] if body_subject else '(空)'}")

        print(f"    正文长度: {len(body_text)} 字符")
        print(f"    正文预览: {body_text[:120]}...")

        # --- LLM 分析 ---
        # 使用外层主题（subject）+ 内层主题（body_subject）+ 正文
        analysis_subject = subject or body_subject
        analysis_body = body_text
        print(f"    分析主题: {analysis_subject[:60]}")
        print(f"    分析正文长度: {len(analysis_body)} 字符")
        print(f"    调用 LLM 分析...")
        try:
            analysis = analyzer.analyze(analysis_subject, analysis_body)
        except Exception as e:
            print(f"    FAIL: {e}")
            analysis = {"action": "error", "reason": str(e), "sn": None}

        action = analysis.get("action", "unknown")
        confidence = analysis.get("confidence", 0)
        reason = analysis.get("reason", "")
        sn = analysis.get("sn", "")
        model = analysis.get("_model", "")

        action_color = {"edm_process": "✓", "ignore": "✗", "error": "!"}.get(action, "?")
        print(f"    结果: {action_color} {action} (置信度 {confidence}%)")
        print(f"    理由: {reason}")
        if sn:
            print(f"    SN:   {sn}")

        results.append({
            "item_id": item_id,
            "subject": body_subject,
            "sender": sender,
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "sn": sn,
        })

    # --- 汇总 ---
    print(f"\n{'=' * 60}")
    print("分析汇总")
    print(f"{'=' * 60}")

    edm_count = sum(1 for r in results if r["action"] == "edm_process")
    ignore_count = sum(1 for r in results if r["action"] == "ignore")

    print(f"通过过滤: {len(passed_items)}")
    print(f"LLM 判定为 EDM 处理: {edm_count}")
    print(f"LLM 判定为忽略: {ignore_count}")

    if results:
        print(f"\n{'ID':<10} {'动作':<14} {'置信度':<8} {'SN':<12} {'主题'}")
        print("─" * 80)
        for r in results:
            print(f"{r['item_id'][:10]:<10} {r['action']:<14} {r['confidence']:<8} {str(r.get('sn','')):<12} {r['subject'][:45]}")


# ===================================================================
# Main
# ===================================================================

if __name__ == "__main__":
    try:
        passed = test_ews_and_filter()
        test_llm_analysis(passed)
    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
