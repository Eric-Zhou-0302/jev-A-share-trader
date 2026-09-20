from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from pathlib import Path

from .config import data_directory, load_settings, public_settings, save_settings
from .export import export_analysis, localize
from .models import AnalysisError, normalize_symbol
from .service import Engine


def main():
    parser = argparse.ArgumentParser(description="Jev A-share technical analysis / A 股技术分析")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--lang", choices=["zh", "en"], default="zh")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动本地网页 / Start the local workbench")
    serve.add_argument("--port", type=int, default=8765)
    analyze = commands.add_parser("analyze", help="分析个股 / Analyze a stock")
    analyze.add_argument("symbol")
    analyze.add_argument("--technical-only", action="store_true")
    analyze.add_argument("--format", choices=["json", "csv", "html"])
    analyze.add_argument("--output", type=Path)
    watch = commands.add_parser("watch", help="管理自选股 / Manage the watchlist")
    watch.add_argument("operation", choices=["list", "add", "remove"], default="list", nargs="?")
    watch.add_argument("symbol", nargs="?")
    scan = commands.add_parser("scan", help="全市场或自选股扫描 / Scan the market or watchlist")
    scan.add_argument("--scope", choices=["market", "watchlist"], default="watchlist")
    scan.add_argument("--resume")
    scan.add_argument("--retry", action="store_true")
    commands.add_parser("jobs", help="查看扫描记录 / List scan jobs")
    config = commands.add_parser("configure", help="配置数据源和凭据 / Configure providers and credentials")
    config.add_argument("--show", action="store_true")
    config.add_argument("--provider", choices=["akshare", "tushare"])
    config.add_argument("--tushare-token", action="store_true", help="隐藏输入 Tushare Token / Prompt for a Tushare token")
    config.add_argument("--jev-key", action="store_true", help="隐藏输入 Jev API key / Prompt for a Jev key")
    args = parser.parse_args()
    directory = args.data_dir or data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    if args.command == "configure":
        settings = load_settings(directory)
        if not args.show:
            from pydantic import SecretStr
            if args.provider:
                settings.provider = args.provider
            if args.tushare_token or (settings.provider == "tushare" and not settings.tushare_token.get_secret_value()):
                token = getpass.getpass("Tushare Token: ").strip()
                if token:
                    settings.tushare_token = SecretStr(token)
            if settings.provider == "tushare" and not settings.tushare_token.get_secret_value():
                parser.error("Tushare requires a token / Tushare 需要 Token")
            if args.jev_key or (not args.provider and not args.tushare_token):
                key = getpass.getpass("Jev API key: ").strip()
                if key:
                    settings.jev_api_key = SecretStr(key)
            save_settings(directory, settings)
        print(json.dumps(public_settings(settings), ensure_ascii=False, indent=2))
        return
    if args.command == "serve":
        import uvicorn

        from .api import create_app
        print(f"Jev → http://127.0.0.1:{args.port}")
        uvicorn.run(create_app(directory), host="127.0.0.1", port=args.port)
        return
    engine = Engine(directory)
    try:
        if args.command == "analyze":
            result = engine.analyze(args.symbol, technical_only=args.technical_only)
            if args.output or args.format:
                rendered = export_analysis(result, args.format or "html", args.lang)
                if args.output:
                    args.output.write_text(rendered, encoding="utf-8")
                    print(args.output.resolve())
                else:
                    print(rendered)
            else:
                data = localize(result, args.lang)
                print(f"{data['name']} {data['symbol']} · {data['as_of']}\n{data['action']} · {data['horizon'] or '—'}")
                for item in data["evidence"]:
                    if result.action is None or item["side"] != ("Context" if args.lang == "en" else "背景证据"):
                        print(f"[{item['side']}] {item['text']} ({item['date']})")
                for value in data["notices"]:
                    print(value)
            if result.action is None and not args.technical_only:
                raise SystemExit(2)
        elif args.command == "watch":
            if args.operation != "list":
                if not args.symbol:
                    parser.error("watch add/remove requires a symbol")
                if args.operation == "remove":
                    engine.store.watch(normalize_symbol(args.symbol), "", remove=True)
                else:
                    stock = engine.get_stock(args.symbol)
                    engine.store.watch(stock.symbol, stock.name)
            print(json.dumps(engine.store.watchlist(), ensure_ascii=False, indent=2))
        elif args.command == "jobs":
            for job in engine.store.jobs():
                print(job["id"], job["scope"], job["status"], job["as_of"])
        elif args.command == "scan":
            from .jobs import JobManager
            manager = JobManager(engine)
            if args.resume:
                job = manager.resume(args.resume, retry_failed=args.retry)
            else:
                symbols = [item["symbol"] for item in engine.store.watchlist()] if args.scope == "watchlist" else None
                if symbols == []:
                    raise AnalysisError("empty_watchlist", "请先添加自选股。", "Add stocks to the watchlist first.")
                job = manager.start(symbols)
            last = None
            try:
                while manager.active:
                    snapshot = manager.get(job["id"])
                    current = (snapshot["phase"], snapshot["downloaded"], snapshot["completed"], snapshot["failed"], snapshot["skipped"])
                    if current != last:
                        phase = {"preparing": "准备中", "data": "同步行情", "analysis": "生成分析"}.get(snapshot["phase"], snapshot["phase"]) if args.lang == "zh" else snapshot["phase"]
                        labels = ("行情", "完成", "失败", "跳过") if args.lang == "zh" else ("data", "ready", "failed", "skipped")
                        print(f"{job['id']} | {phase} | {labels[0]}={snapshot['downloaded']}/{snapshot['total']} {labels[1]}={snapshot['completed']} {labels[2]}={snapshot['failed']} {labels[3]}={snapshot['skipped']}", flush=True)
                        last = current
                    time.sleep(.5)
            except KeyboardInterrupt:
                manager.pause(job["id"])
                print("当前请求结束后暂停…" if args.lang == "zh" else "Pausing after the current request…", file=sys.stderr)
                while manager.active:
                    time.sleep(.2)
            final = manager.get(job["id"])
            statuses = {"completed": "已完成", "partial": "部分完成", "paused": "已暂停", "failed": "失败", "stopped": "已中止"}
            print(statuses.get(final["status"], final["status"]) if args.lang == "zh" else final["status"])
            if final.get("error"):
                print(final["error"][args.lang])
            if final["status"] != "completed":
                raise SystemExit(2)
    except AnalysisError as exc:
        print(exc.message(args.lang), file=sys.stderr)
        raise SystemExit(2) from exc
    finally:
        engine.close()


if __name__ == "__main__":
    main()
