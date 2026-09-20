from __future__ import annotations

import csv
import html
import io
import json

from .models import GROUP_NAMES, Analysis

ACTIONS = {"buy": ("买入", "Buy"), "hold": ("持有", "Hold"), "sell": ("卖出", "Sell")}
SIDES = {"support": ("支持证据", "Supporting evidence"), "oppose": ("反对证据", "Opposing evidence"), "context": ("背景证据", "Context")}


def localize(result: Analysis, language="zh") -> dict:
    index = int(language == "en")
    return {
        "symbol": result.symbol, "name": result.name, "as_of": result.as_of, "source": result.source,
        "status": result.status, "action": ACTIONS[result.action][index] if result.action else ("未形成判断", "No decision")[index],
        "horizon": (f"未来 {result.horizon} 个交易日" if index == 0 else f"Next {result.horizon} trading sessions") if result.horizon else None,
        "evidence": [{"side": SIDES[item.side][index], "group": GROUP_NAMES.get(item.group, ("汇总", "Aggregate"))[index], "date": item.date, "text": item.en if index else item.zh} for item in result.evidence],
        "notices": [item["en" if index else "zh"] for item in result.notices],
        "meaning": ("持有对未持仓者表示观望；卖出对未持仓者表示回避。适用周期是分析窗口，不是延迟执行期限。", "Without a position, Hold means wait and Sell means avoid. The horizon is an analysis window, not an instruction to delay an action.")[index],
    }


def export_analysis(result: Analysis, kind: str, language="zh") -> str:
    data = localize(result, language)
    if kind == "json":
        return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if kind == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["symbol", "name", "as_of", "action", "horizon", "side", "group", "evidence_date", "evidence"] if language == "en" else ["股票代码", "股票名称", "数据截止", "总判断", "适用周期", "证据方向", "技术维度", "证据日期", "技术证据"])
        for item in data["evidence"]:
            # CSV 输出为用户可打开的文本，防止上游股票名称被电子表格解释为公式。
            row = [data["symbol"], data["name"], data["as_of"], data["action"], data["horizon"] or "", item["side"], item["group"], item["date"], item["text"]]
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value for value in row])
        return "\ufeff" + output.getvalue()
    if kind != "html":
        raise ValueError("unsupported export format")
    escape = html.escape
    sections = []
    for side in SIDES:
        label = SIDES[side][int(language == "en")]
        items = [item for item in data["evidence"] if item["side"] == label]
        if not items:
            continue
        sections.append(f"<section><h2>{label}</h2><ul>" + "".join(f"<li><small>{escape(item['group'])} · {escape(item['date'])}</small><p>{escape(item['text'])}</p></li>" for item in items) + "</ul></section>")
    notices = "".join(f"<p>{escape(value)}</p>" for value in data["notices"])
    return f"""<!doctype html><html lang="{'en' if language == 'en' else 'zh-CN'}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Jev · {escape(data['symbol'])}</title><style>body{{font:16px/1.65 system-ui,sans-serif;max-width:900px;margin:48px auto;padding:0 24px;color:#172322;background:#f5f7f5}}header,section,footer{{background:white;border:1px solid #dce3df;padding:24px;margin:20px 0;border-radius:12px}}h1{{margin:4px 0}}h2{{font-size:18px}}small,footer{{color:#566964}}li{{margin:16px 0}}p{{margin:5px 0}}strong{{font-size:26px;color:#267766}}@media print{{body{{background:white;margin:0}}section{{break-inside:avoid}}}}</style><header><small>JEV / A-SHARE TRADER</small><h1>{escape(data['name'])} <small>{escape(data['symbol'])}</small></h1><p>{escape(data['as_of'])} · {escape(data['source'])}</p><strong>{escape(data['action'])}</strong><p>{escape(data['horizon'] or '')}</p></header>{''.join(sections)}<footer>{notices}<p>{escape(data['meaning'])}</p></footer></html>"""
