from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import Settings, data_directory, public_settings, save_settings
from .export import export_analysis
from .jobs import JobManager
from .models import Analysis, AnalysisError, normalize_symbol
from .providers import create_provider
from .service import Engine


class AnalyzeInput(BaseModel):
    symbol: str
    technical_only: bool = False


class ScanInput(BaseModel):
    scope: Literal["batch", "watchlist"] = "batch"
    symbols: str | list[Annotated[str, Field(max_length=32)]] | None = Field(default=None, max_length=20000)


class WatchInput(BaseModel):
    symbol: str


class DeleteInput(BaseModel):
    ids: list[Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]] = Field(min_length=1, max_length=100)


class RestoreInput(BaseModel):
    token: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]+$")


class ConfigInput(BaseModel):
    provider: Literal["akshare", "tushare"] | None = None
    tushare_token: str | None = Field(default=None, max_length=512)
    model: str = Field(default="jev-latest", min_length=1, max_length=100)
    jev_api_key: str | None = Field(default=None, max_length=512)
    markets: list[Literal["SH", "SZ", "BJ"]] = Field(default_factory=lambda: ["SH", "SZ", "BJ"])
    exclude_special: bool = True
    min_amount: float = Field(default=0, ge=0)
    language: Literal["zh", "en"] = "zh"


def create_app(directory: Path | None = None, supplied_engine=None) -> FastAPI:
    directory = directory or data_directory()
    engine = supplied_engine or Engine(directory)
    manager = JobManager(engine)

    @asynccontextmanager
    async def lifespan(app):
        yield
        manager.shutdown()
        engine.close()

    app = FastAPI(title="Jev A-share trader", version=__version__, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
    app.state.engine, app.state.jobs = engine, manager

    @app.middleware("http")
    async def local_write_guard(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            allowed = {f"{request.url.scheme}://{request.headers.get('host')}", "http://127.0.0.1:5173", "http://localhost:5173"}
            if origin and origin not in allowed:
                return JSONResponse({"code": "origin_rejected", "message": "Cross-origin writes are not allowed."}, status_code=403)
            if request.method != "DELETE" and "application/json" not in request.headers.get("content-type", ""):
                return JSONResponse({"code": "content_type", "message": "JSON is required."}, status_code=415)
        return await call_next(request)

    @app.exception_handler(AnalysisError)
    async def analysis_error(request: Request, exc: AnalysisError):
        return JSONResponse({"code": exc.code, "message": exc.message(request.query_params.get("lang", "zh"))}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # 默认验证响应会回显 input；设置请求中可能含用户凭据。
        message = "Invalid request fields." if request.query_params.get("lang") == "en" else "请求字段无效，请检查输入。"
        return JSONResponse({"code": "invalid_request", "message": message}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "provider": engine.settings.provider, "jev_configured": bool(engine.settings.jev_api_key.get_secret_value())}

    @app.get("/api/settings")
    def settings():
        return public_settings(engine.settings)

    @app.put("/api/settings")
    def update_settings(body: ConfigInput):
        with engine.analysis_lock:
            if manager.is_running():
                raise AnalysisError("job_active", "请先暂停扫描，再修改配置。", "Pause the scan before changing configuration.")
            raw = engine.settings.model_dump()
            update = body.model_dump(exclude={"jev_api_key", "tushare_token"}, exclude_unset=True)
            if update.get("provider") is None:
                update.pop("provider", None)
            if not body.markets:
                raise AnalysisError("invalid_config", "至少选择一个交易所。", "Select at least one exchange.")
            if body.jev_api_key is not None and body.jev_api_key.strip():
                update["jev_api_key"] = body.jev_api_key.strip()
            if body.tushare_token is not None and body.tushare_token.strip():
                update["tushare_token"] = body.tushare_token.strip()
            raw.update(update)
            validated = Settings.model_validate(raw)
            if validated.provider == "tushare" and not validated.tushare_token.get_secret_value():
                raise AnalysisError("needs_tushare_token", "选择 Tushare 前请先填写 Token。", "Enter a Tushare token before selecting Tushare.")
            changed = (validated.provider != engine.settings.provider
                       or validated.tushare_token != engine.settings.tushare_token)
            replacement = create_provider(validated, engine.store) if changed else None
            try:
                save_settings(directory, validated)
            except Exception:
                if replacement:
                    replacement.close()
                raise
            previous = engine.provider
            if replacement:
                engine.provider = replacement
            engine.settings = validated
            engine.client.settings = validated
            if hasattr(engine.provider, "settings"):
                engine.provider.settings = validated
            if replacement:
                previous.close()
            return public_settings(validated)

    @app.get("/api/stocks")
    def stocks(q: str = Query(default="", max_length=60), market: str = "", limit: int = Query(default=30, ge=1, le=200)):
        with engine.analysis_lock:
            universe = engine.provider.universe()
        query = q.strip().lower()
        found = [stock for stock in universe if (not market or stock.market == market) and (not query or query in stock.symbol.lower() or query in stock.name.lower())]
        return {"total": len(universe), "matches": len(found), "items": [stock.model_dump() for stock in found[:limit]]}

    @app.get("/api/watchlist")
    def watchlist():
        return engine.store.watchlist()

    @app.post("/api/watchlist")
    def add_watch(body: WatchInput):
        with engine.analysis_lock:
            stock = engine.get_stock(body.symbol)
        engine.store.watch(stock.symbol, stock.name)
        return engine.store.watchlist()

    @app.delete("/api/watchlist/{symbol}")
    def remove_watch(symbol: str):
        engine.store.watch(normalize_symbol(symbol), "", remove=True)
        return engine.store.watchlist()

    @app.post("/api/analyze")
    def analyze(body: AnalyzeInput):
        return engine.analyze(body.symbol, technical_only=body.technical_only)

    @app.get("/api/analyses")
    def history(symbol: str | None = None):
        return engine.store.summaries(normalize_symbol(symbol) if symbol else None)

    @app.get("/api/analyses/search")
    def search_history(q: str = Query(default="", max_length=60), date_from: date | None = None,
                       date_to: date | None = None, page: int = Query(default=0, ge=0),
                       limit: int = Query(default=50, ge=1, le=100)):
        if date_from and date_to and date_from > date_to:
            raise AnalysisError("invalid_date_range", "开始日期不能晚于结束日期。", "The start date must not be after the end date.")
        return engine.store.search_summaries(q, date_from.isoformat() if date_from else None,
                                            date_to.isoformat() if date_to else None, page, limit)

    @app.get("/api/analyses/{identifier}")
    def analysis(identifier: str):
        saved = engine.store.analysis(identifier)
        if not saved:
            raise AnalysisError("analysis_missing", "找不到分析记录。", "Analysis not found.")
        return saved

    @app.post("/api/analyses/delete")
    def delete_analyses(body: DeleteInput):
        with engine.analysis_lock:
            return engine.store.delete_records("analysis", body.ids)

    @app.post("/api/analyses/restore")
    def restore_analyses(body: RestoreInput):
        with engine.analysis_lock:
            return engine.store.restore_records("analysis", body.token)

    @app.get("/api/analyses/{identifier}/export")
    def export(identifier: str, format: Literal["json", "csv", "html"] = "html", lang: Literal["zh", "en"] = "zh"):
        saved = analysis(identifier)
        result = Analysis.model_validate(saved)
        body = export_analysis(result, format, lang)
        content_type = {"json": "application/json", "csv": "text/csv", "html": "text/html"}[format]
        return Response(body, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="jev-{result.symbol}-{result.as_of}-{lang}.{format}"'})

    @app.get("/api/jobs")
    def jobs():
        return manager.list()

    @app.post("/api/jobs")
    def start_scan(body: ScanInput):
        if body.scope == "watchlist" and body.symbols is not None:
            raise AnalysisError("invalid_scope", "自选股扫描不接受额外列表，请选择股票列表。", "Use the stock-list scope to submit symbols.")
        symbols = [stock["symbol"] for stock in engine.store.watchlist()] if body.scope == "watchlist" else body.symbols
        if body.scope == "watchlist" and not symbols:
            raise AnalysisError("empty_watchlist", "请先添加自选股。", "Add stocks to the watchlist first.")
        return manager.start(symbols, scope=body.scope)

    @app.get("/api/jobs/search")
    def scan_history(scope: Literal["all", "batch", "market", "watchlist"] = "all",
                     status: Literal["all", "preparing", "running", "pausing", "paused", "completed", "partial", "failed", "stopping", "stopped", "resetting", "reset"] = "all",
                     page: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
        return manager.search(scope, status, page, limit)

    @app.get("/api/jobs/{identifier}")
    def job(identifier: str):
        return manager.get(identifier)

    @app.post("/api/jobs/delete")
    def delete_jobs(body: DeleteInput):
        return manager.delete(body.ids)

    @app.post("/api/jobs/restore")
    def restore_jobs(body: RestoreInput):
        return manager.restore(body.token)

    @app.post("/api/jobs/{identifier}/{operation}")
    def control_job(identifier: str, operation: Literal["pause", "resume", "retry", "stop", "reset"]):
        manager.get(identifier)
        if operation in ("stop", "reset"):
            return manager.stop(identifier)
        return manager.pause(identifier) if operation == "pause" else manager.resume(identifier, retry_failed=operation == "retry")

    web = Path(__file__).parent / "web"
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse)
        def missing_build():
            return "<h1>Jev</h1><p>Build the web interface: cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</p>"
    return app
