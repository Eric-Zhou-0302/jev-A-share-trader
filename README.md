<h1 align="center">jev-A-share-trader</h1>

<p align="center"><strong>基于 Jev 的 A 股技术分析工作台</strong></p>
<p align="center">从价格与成交量，读懂市场结构。</p>
<p align="center">
  <a href="https://github.com/Eric-Zhou-0302/jev-A-share-trader/actions/workflows/ci.yml"><img src="https://github.com/Eric-Zhou-0302/jev-A-share-trader/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3d6047" alt="MIT License" /></a>
  <a href="https://github.com/Eric-Zhou-0302/jev-A-share-trader/tree/v0.1.1"><img src="https://img.shields.io/badge/version-0.1.1-3d6047" alt="v0.1.1" /></a>
</p>
<p align="center">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
  <br />
  <a href="#快速开始">快速开始</a> · <a href="#技术分析覆盖">技术指标</a> · <a href="docs/methodology.md">分析方法</a> · <a href="docs/usage.md">使用指南</a>
</p>

---

**八个分析维度，一份可追溯的判断。**

`jev-A-share-trader` 使用 AKShare 或 Tushare 获取 A 股行情，计算技术指标与形态证据，由 Jev 评估各个维度，再汇总为一个买入、持有或卖出判断。你可以分析一只股票、跟踪自选股，也可以扫描沪深京市场。

每份分析围绕三个问题展开：

| 总判断 | 适用周期 | 技术证据 |
| --- | --- | --- |
| **买入 / 持有 / 卖出** | 自动选择 **2–5** 或 **5–20 个交易日** | 同时呈现支持、反对与背景证据，可定位到对应 K 线 |

分析基于最近已完成交易日的数据。盘中运行时，使用上一交易日及之前的日线；周线、月线也只使用已经结束的周期。

## 主要功能

- **个股分析** — 按代码或名称查找股票，查看日／周／月 K 线，切换均线、布林带、成交量、MACD 和 RSI，逐项核对指标与证据。
- **自选与市场扫描** — 覆盖沪深京 A 股，支持进度查看、暂停、恢复与失败重试；默认过滤 ST、退市整理、无成交及历史不足的股票。
- **两种数据源** — 内置 AKShare 与 Tushare Pro，可在设置中切换；保留自定义行情接口。
- **网页与命令行** — 共用本地自选股、分析记录与扫描任务，支持 JSON、CSV、HTML 导出。
- **中英双语** — 界面及报告默认中文，可切换英文。

## 快速开始

需要 **Python 3.11+**；使用网页还需要 **Node.js 22.12+**。支持 macOS、Linux；Windows 请使用 WSL。建议在自己选择的 Python 虚拟环境中安装。

### 1. 安装并启动

克隆项目并进入项目根目录：

```bash
git clone https://github.com/Eric-Zhou-0302/jev-A-share-trader.git
cd jev-A-share-trader
python -m pip install -e .
npm --prefix frontend ci
npm --prefix frontend run build
jev serve
```

打开 **[http://127.0.0.1:8765](http://127.0.0.1:8765)**。

只使用命令行时，安装 Python 包即可，无需 Node.js 或前端构建。

### 2. 配置自己的接口

在网页 **设置** 中填写 Jev API key，并选择数据源：

| 服务 | 用途 | 凭据 |
| --- | --- | --- |
| Jev / TypeSafe | 对技术状态进行结构化评估 | 自己的 API key |
| AKShare（默认） | 获取行情与参考数据 | 无需 API key |
| Tushare Pro | 获取行情与参考数据 | 自己的 Token，且具备所用接口的权限 |

也可以通过命令行隐藏输入凭据：

```bash
jev configure
jev configure --provider tushare --tushare-token
```

第一条配置 Jev；第二条仅在使用 Tushare 时执行。环境变量也支持 `TYPESAFE_API_KEY` 和 `TUSHARE_TOKEN`，优先于本地配置。

**暂不配置 Jev，也能查看 K 线、技术指标和偏多／偏空事实。** 此时显示“未形成判断”，不会以默认结论代替模型结果。

### 3. 开始分析

在工作台输入股票代码，例如 `000001`，点击“开始分析”。也可以直接运行：

```bash
jev analyze 000001
```

## 技术分析覆盖

指标按八个维度组织，保留相互支持与冲突的信息，而不是将所有指标简单计票。

| 维度 | 主要指标与分析内容 |
| --- | --- |
| **趋势** | SMA / EMA 5、10、20、60、120、250；WMA、HMA、KAMA；DMI / ADX、Aroon、SAR、Supertrend；均线斜率与交叉 |
| **动量** | MACD、RSI 6/14/24、KDJ、Stochastic、CCI、Williams %R、ROC、MOM、TRIX、TSI；确认拐点上的背离候选 |
| **量价** | 均量、量比、换手率、OBV、MFI、CMF、A/D、ADOSC、PVT、VWMA；量价确认 |
| **波动** | ATR / NATR、Bollinger、Keltner、Donchian、历史波动率、带宽、%B、波动挤压 |
| **价格结构** | 区间位置、确认高低点、趋势线、突破维持／失败、尚未回补的缺口 |
| **K 线形态** | 实体与影线；十字星、锤头、吞没、早晚星、孕线、三白兵、三只乌鸦等 14 类形态 |
| **多周期** | 完整周线 MA10/20、月线 MA6/12；不同周期的共振与冲突 |
| **相对强弱** | 相对沪深300及所属行业的 5/20/60 日表现、相关性、指数趋势、股票池市场宽度 |

行业、周月线和市场宽度等参考信息取决于数据权限、历史长度与样本覆盖。缺失会明确标注，不以零值代替。完整参数、形态定义及数据口径见 [分析方法](docs/methodology.md)。

## Jev 如何参与

```text
AKShare / Tushare
       ↓
已完成的行情数据
       ↓
Python 计算指标、识别形态、生成技术事实
       ↓
Jev 按维度评估两个候选周期
       ↓
代码汇总方向、分歧与波动风险
       ↓
一个总判断 + 一个适用周期 + 支持与反对证据
```

Jev 接收结构化技术状态。指标计算、证据日期和最终汇总规则均可检查；模型或必要行情失败时，不输出买入／持有／卖出判断。没有技术信号预筛选，扫描中每只通过基础数据校验与过滤的股票都会进入模型评估。

工作台和记录保存在本机，行情获取及 Jev 推理需要联网，技术状态会发送至 TypeSafe。项目不提供、托管或转售行情；数据权限及模型调用费用由使用者自己的账户承担。

## 命令行

```bash
# 仅查看技术事实，不调用 Jev
jev analyze 000001 --technical-only

# 导出英文 HTML 报告，也支持 json / csv
jev --lang en analyze 000001 --format html --output analysis.html

# 添加自选并扫描
jev watch add 000001
jev scan --scope watchlist

# 扫描全市场
jev scan --scope market

# 查看任务，恢复并重试失败项
jev jobs
jev scan --resume JOB_ID --retry
```

扫描可用 `Ctrl+C` 暂停。全市场扫描会产生较多行情请求与模型调用；可先从个股或自选股开始。更多命令、缓存行为和恢复条件见 [使用指南](docs/usage.md)。

## 文档与开发

| 文档 | 内容 |
| --- | --- |
| [使用指南](docs/usage.md) | 配置、CLI、扫描恢复、本地数据与常见问题 |
| [分析方法](docs/methodology.md) | 数据时点、指标公式、Jev 问题与汇总规则 |
| [数据源与扩展](docs/providers.md) | AKShare / Tushare 接口及自定义提供方契约 |
| [需求规格](docs/requirements.md) | 产品范围与交互约定 |
| [更新日志](CHANGELOG.md) | 版本记录与功能变化 |
| [参与贡献](CONTRIBUTING.md) | 开发流程、验证方式与 PR 约定 |

技术栈：Python · FastAPI · pandas · TA-Lib · SQLite · React · TypeScript · Vite。

<details>
<summary>本地开发与检查</summary>

在项目根目录执行：

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests
npm --prefix frontend run build
```

前端开发时，在一个终端运行 `jev serve`，另一个终端运行 `npm --prefix frontend run dev`。打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)，API 请求会代理至后端。后端交互式 API 文档位于 [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)。

</details>

## Jev 生态与参与

项目直接调用 TypeSafe System One API，使用 `Choice` 判断各维度方向、`Noul` 评估波动风险。调用与校验见 [jev.py](src/jev_trader/jev.py)，对应验证见 [test_jev.py](tests/test_jev.py)。Jev 的使用方式可参考 [官方文档](https://docs.typesafe.ai/introduction)；更多社区项目可在 [Awesome Jev](https://awesomejev.com/) 中发现。

欢迎通过 [Issue](https://github.com/Eric-Zhou-0302/jev-A-share-trader/issues) 和 Pull Request 参与，详见 [贡献指南](CONTRIBUTING.md)。本项目独立开发，与 TypeSafe AI 无隶属关系。

## 项目边界

当前专注于最新收盘状态下的技术研究，不包含回测系统、持仓管理、自动下单或买入价／止损价／目标价。判断规则尚未经过收益回测，Jev 输出的概率不等于交易胜率。服务面向本地个人使用，不包含公网多用户认证。

项目代码采用 [MIT 许可证](LICENSE)。图表由 TradingView Lightweight Charts 提供，相关 [第三方许可](licenses/lightweight-charts-LICENSE.txt) 与 [版权声明](licenses/lightweight-charts-NOTICE.txt) 随项目保留。
