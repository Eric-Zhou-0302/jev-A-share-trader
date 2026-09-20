# Contributing / 参与贡献

欢迎通过 Issue 和 Pull Request 改进项目，中文或英文均可。适合参与的方向包括指标正确性、数据源兼容性、错误处理、界面可用性、翻译和文档。

Issues and pull requests are welcome in Chinese or English. Useful contributions include indicator correctness, provider compatibility, error handling, usability, translations, and documentation.

## 开始之前 / Before you start

- 搜索已有 Issue 和 PR，避免重复。范围较大的改动先开 Issue 讨论。
- 提交最小复现步骤；不要附带 API key、Token、本机配置或真实账户资料。
- 当前范围为最新收盘技术分析。回测、持仓管理、下单和交易价位需要单独讨论产品范围。

Search existing issues and PRs first. Discuss larger changes before implementing them. Include a minimal reproduction without credentials or private account data. Backtesting, portfolios, order execution, and trade-price levels require a separate scope discussion.

## 开发 / Development

从项目根目录运行，使用自己选择的 Python 虚拟环境：

Run from the repository root in a Python virtual environment of your choice:

```bash
python -m pip install -e '.[dev]'
npm --prefix frontend ci
npm --prefix frontend run build
jev serve
```

前端热更新可另开终端运行 `npm --prefix frontend run dev`。环境要求和使用说明见 [README](README.md) / [English README](README.en.md)。

For frontend hot reload, run `npm --prefix frontend run dev` in a second terminal. See the READMEs for requirements and configuration.

## 验证 / Validation

```bash
python -m pytest -q
python -m ruff check src tests
npm --prefix frontend run build
git diff --check
```

测试使用本地 fixture 和模拟 HTTP 响应，无需真实 Jev key 或 Tushare Token。验证与改动相关的行为即可；界面修改还应检查中英切换。CI 检查 Linux 的 Python 3.11 / 3.14、macOS 的 Python 3.14，以及 Node.js 22 下的前端构建。

Tests use local fixtures and mock HTTP responses without live Jev or Tushare credentials. Validate behavior relevant to the change; UI changes also need Chinese / English checks. CI covers Python 3.11 / 3.14 on Linux, Python 3.14 on macOS, and a frontend build on Node.js 22.

## 技术约束 / Technical constraints

- 只使用已完成交易日和完整周／月线；必要数据或模型失败不能默认输出“持有”。
- 新增指标需说明公式、参数和缺失值行为，并更新 [分析方法](docs/methodology.md)。
- 修改行情接口需核验成交量、成交额、换手率和复权口径，遵循 [数据提供方契约](docs/providers.md)。
- 支持与反对证据都应保留，不能为了匹配总判断删除冲突信息。
- 不提交密钥、运行数据库、环境目录、生成的前端文件或付费接口的私有响应。

Use completed sessions and periods only. Required-data or model failures must not become Hold decisions. Document indicator formulas and missing values; verify provider units and adjustment conventions. Preserve opposing evidence. Keep credentials, runtime data, environments, generated assets, and private API responses out of commits.

## 提交 PR / Pull requests

让每个 PR 围绕一个明确问题，说明行为变化、验证结果和未验证的限制。涉及界面文案或 README 时同步中英文。不要宣称尚未实测的收益、胜率、延迟或成本。

Keep each PR focused on one problem. Explain behavior changes, actual validation, and remaining limits. Update both languages when changing UI text or READMEs. Do not claim unmeasured returns, accuracy, latency, or costs.

提交前请核对代码、文档和测试的一致性。本地验证记录不代表已经验证交易收益或所有上游接口。

Check that code, documentation, and tests agree before submitting. Local validation does not establish trading profitability or universal upstream availability.
