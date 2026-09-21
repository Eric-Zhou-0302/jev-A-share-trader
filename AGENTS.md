# Project guidance

- Python 后端使用项目 `.venv`；React 前端位于 `frontend`，npm 依赖在该目录内安装。
- 产品约束见 `docs/requirements.md`，公式与汇总规则见 `docs/methodology.md`，扩展行情契约见 `docs/providers.md`。
- 只使用已完成交易日及完整周／月线。模型或必需数据失败时，不得默认输出持有，不得在正常界面生成模拟行情或 Jev 响应。
- 用户输出限一个判断、一个适用周期和证据；不增加交易价位、持仓、执行或回测，除非用户改变范围。
- AKShare 主备源独立缓存；改动源接口或升级其依赖时重新核验量、额、换手率和复权口径。
- 凭据仅使用环境变量或本机配置，不能提交、打印或放入浏览器持久化存储。
- 核心逻辑验证：`.venv/bin/pytest -q`、`.venv/bin/ruff check src tests`。界面验证：在 `frontend` 执行 `npm run build`，并检查实际浏览器的中英切换及完整使用流程。
- `.qa` 为隔离验收资料，`.data` 为可选本地数据目录，均不进入版本控制。批量扫描会调用用户模型，应使用小规模测试或 mock 验证实现，避免未明确要求的付费批量运行。
