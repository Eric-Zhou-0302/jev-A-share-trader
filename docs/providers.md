# 扩展行情提供方

内置 AKShare（默认）和 Tushare Pro。接口定义在 `src/jev_trader/providers/__init__.py`，数据获取与技术分析分离。

## 数据契约

| 方法 | 返回内容 |
| --- | --- |
| `universe()` | `list[Stock]`，规范代码如 `600000.SH`、`000001.SZ`、`920001.BJ`；名称、交易所、板块、ST／退市标记 |
| `calendar()` | 完整交易日 `list[date]`，需覆盖当前年度后续日期以正确识别完整周／月；不可仅用周一至周五代替节假日历 |
| `bars(symbol, as_of)` | `(DataFrame, source_label)`，同口径前复权OHLC、原始成交量，必须明确截至哪天 |
| `metadata(stock)` | 补充行业归属／上市日期的 `Stock`；不得用实时行情字段作为已完成日线 |
| `benchmark(as_of)` | 沪深300日线 `DataFrame` |
| `industry(name, as_of)` | 与 `metadata` 行业分类同口径的行业指数日线 |
| `close()` | 释放会话、工作进程等 |

日线列：`date, open, high, low, close, volume, amount, turnover`。日期为 `YYYY-MM-DD`；成交量为**股**，成交额为**元**，换手率为**百分数**。可选 `amount/turnover` 不可用时为缺失值，不能置零。股票价格不得混接不同复权基准。指数只用其价格，不把指数成交量与个股成交量比较。

可选参考数据不可用时抛出 `AnalysisError(code, zh, en)`，由服务层明确显示缺失；个股必需数据失败则停止判断。异常文字不包含 token、认证 URL 或请求头。至少对带超时的网络请求、限流与重试作出清楚处理。

## 安装式扩展

在你的提供方包中定义接收 `(settings, store)` 的类，实现上述接口，并注册 Python entry point：

```toml
[project.entry-points."jev_trader.providers"]
my_provider = "my_market_package:MyProvider"
```

安装到本项目环境后，编辑本机 `settings.json`：

```json
{
  "provider": "my_provider",
  "provider_options": {
    "api_key_env": "MY_MARKET_API_KEY"
  }
}
```

由扩展自行读取 `settings.provider_options` 指定的环境变量。此处 `api_key_env` 只是示例约定，核心不会代替扩展猜测字段或获取用户凭据。也可在自定义启动入口调用 `register_provider("my_provider", MyProvider)`。

配置支持合并默认值，以上文件仅是示例；修改已有文件时保留其余用户配置。更换提供方后重启后端。核心 API 不返回 `provider_options`，避免其内部凭据泄露；不在浏览器 localStorage 中保存凭据。

## 内置 AKShare 边界

东方财富／腾讯的日线接口分别使用独立缓存；东财成交量“手”乘100为股，已验证 AKShare 1.18.96 的腾讯接口输出已经是股、换手率为比例，故只将后者乘100。依赖升级后应重新核对这两项，不能按接口名称猜单位。

AKShare 是接入库，公开上游可能限流、改字段或不可用，安装成功不等于所有接口都能访问。接口放在可终止的独立进程中，避免没有 timeout 参数的函数阻塞主服务。单个请求默认25秒、请求间隔0.3秒，默认顺序调用；没有使用高并发抓取或绕过访问控制。

首次实测（2026-09-20）：获取5,564只沪深京股票，000001.SZ截至2026-09-18的2,430根日线及沪深300参考数据；行业元数据接口在本机出现ProxyError，已作为缺失提示处理。后续实际界面验证时东财日线及指数接口也出现ProxyError，个股日线已自动回退到腾讯。接口可用性随用户网络和上游变化，这一记录不保证后续可用。

## 内置 Tushare Pro

选择 `provider: "tushare"`，通过网页设置或 `jev configure --provider tushare --tushare-token` 隐藏输入凭据；也支持 `TUSHARE_TOKEN`。本机配置字段为 `tushare_token`，API 仅返回 `tushare_configured` 布尔值。设置保存后替换正在使用的提供方并关闭旧连接；扫描运行期间拒绝切换，暂停任务在数据源变化后不能恢复，需新建任务。

| 用途 | 接口 | 数据要求 |
| --- | --- | --- |
| 股票名单、上市日期 | `stock_basic` | 按 SSE / SZSE / BSE 分开获取；不使用其行业字段替代申万分类 |
| 交易日历 | `trade_cal` | SSE 日历，保留未来已公布交易日用于完整周月线判断 |
| 个股前复权日线 | `daily` + `adj_factor` | 必须同时可用；按截止日因子重新计算 OHLC |
| 换手率 | `daily_basic` | 可选；失败保留缺失和具体权限／连接提示 |
| 沪深300 | `index_daily`，`000300.SH` | 可选参考；日期必须更新到当前分析截止日 |
| 行业 | `index_member_all` + `sw_daily` | 申万一级分类与同体系指数配对 |

官方 HTTPS 地址固定为 `https://api.tushare.pro`，不跟随重定向，也不回退到明文 HTTP。复用项目的 HTTPX（含 SOCKS 支持），无需增加 SDK 依赖。请求按配置间隔串行，网络异常、HTTP 429 / 5xx 最多三次尝试；鉴权、权限和业务额度错误返回具体且脱敏的提示，不打印上游原始错误。

数据快照按来源／证券／截止日／历史长度隔离。当前实现对新的截止日分窗口重取历史并重算前复权，不进行跨来源或跨复权基准拼接；同一截止日复用完整缓存。更换凭据不改变数据口径或扫描签名，更换提供方会改变签名。

文档核验（2026-09-20）：常用基础接口要求 2000 积分，申万日线要求 5000 积分，具体以账户接口权限为准。自动化验证使用隔离的 HTTP 响应 fixture；未使用用户 Tushare Token 实测完整行情链路。已确认官方 HTTPS 服务可响应无凭据请求并返回鉴权错误。

官方参考：[HTTP 协议](https://tushare.pro/document/1?doc_id=130)、[日线](https://tushare.pro/document/2?doc_id=27)、[复权因子](https://tushare.pro/document/2?doc_id=28)、[每日指标](https://tushare.pro/document/2?doc_id=32)、[申万成分](https://tushare.pro/document/2?doc_id=335)、[申万日线](https://tushare.pro/document/2?doc_id=327)。

AKShare 的大盘指数现已采用东方财富、新浪、腾讯备用顺序；优先复用已完成截止日的独立来源缓存。腾讯指数接口的 `amount` 实际为成交手数，转换为股并将成交额置为缺失，不能误当成元。指数成交量不参与个股量价指标。
