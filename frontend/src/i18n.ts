import type { Lang } from './types'

const zh = {
  title: 'A 股技术分析', subtitle: '收盘之后，看清结构。', workbench: '分析工作台', scans: '市场扫描', history: '分析记录', settings: '设置',
  watchlist: '自选股', addStock: '添加股票', searchPlaceholder: '搜索代码或名称', search: '搜索', emptyWatch: '你的观察，从一只股票开始。', emptyWatchHint: '搜索股票并加入自选，或直接输入代码分析。',
  analyze: '分析', analyzing: '正在获取数据并分析…', batch: '分析自选股', marketScan: '扫描全市场', noSelection: '选择一只股票，展开技术分析。',
  emptyTitle: '从价格与成交量，读懂市场结构。', emptyDescription: '八个分析维度，一份可追溯的判断。使用最近已完成交易日的数据，呈现支持与反对证据。',
  enterSymbol: '输入六位股票代码', startAnalysis: '开始分析', configureJev: '配置 Jev', local: '本地运行', daily: '完整日线', provider: '数据接口', model: '决策模型', connected: '已配置', notConfigured: '待配置',
  feature1: '八维技术分析', feature1Text: '趋势、动量、量价、波动与价格结构，结合形态、多周期及相对强弱。', feature2: '证据可追溯', feature2Text: '每条证据关联指标与日期，同时呈现支持和反对信号。', feature3: '你的数据，你的配置', feature3Text: '行情由你的环境从 AKShare 或 Tushare 获取，Jev 使用你自己的 API key。',
  buy: '买入', hold: '持有', sell: '卖出', noDecision: '未形成判断', horizon: '适用周期', sessions: '个交易日', next: '未来', asOf: '数据截止', source: '数据来源', rows: '历史日线', cached: '复用已有分析', refresh: '重新分析',
  decision: '总判断', support: '支持证据', oppose: '反对证据', context: '背景证据', allEvidence: '全部证据', noEvidence: '当前没有可列举的此类证据。',
  keyHint: '配置自己的 Jev API key 后生成总判断；技术指标与证据仍可查看。',
  priceChart: '价格与技术指标', adjusted: '前复权', day: '日线', week: '周线', month: '月线', completedOnly: '仅使用已完成的 K 线', volume: '成交量', indicator: '副图', overlay: '叠加',
  evidenceTab: '技术证据', indicatorsTab: '指标详情', qualityTab: '数据说明', date: '日期', value: '数值', noValue: '不可用', metrics: '指标', unavailable: '缺失信息', noNotices: '当前分析未发现额外数据缺失。',
  download: '导出', open: '打开', remove: '移出自选', addWatch: '加入自选', close: '关闭', save: '保存配置', saving: '正在保存…', key: 'Jev API key', keyPlaceholder: '输入你的 TypeSafe API key', keySaved: '已保存；留空保持不变',
  keyHelp: '凭据仅保存在本机，不会随分析结果或导出文件返回。', sourceHelp: '公开行情无需 API key；个股日线与大盘指数支持备用来源。', providerHelp: '保存后立即生效。各来源独立缓存，历史分析保留原始来源。', tushareHelp: '使用自己的 Tushare Pro Token。股票名单、日历、复权因子和指数通常需 2000 积分；申万行业日线需 5000 积分，以账户实际权限为准。', tokenPlaceholder: '输入你的 Tushare Pro Token', modelHelp: '模型别名可按 TypeSafe 账户权限配置。',
  exchanges: '交易所范围', excludeSpecial: '默认过滤 ST／退市整理股票', liquidity: '20 日平均成交额下限（元）', liquidityHelp: '0 表示不额外设置成交额过滤。停牌和必要历史不足仍会被排除。',
  scope: '扫描范围', fullMarket: '所选交易所全市场', watchScope: '自选股票池', scanHint: '对每只通过基础过滤的股票调用 Jev，产生完整判断。先同步行情，再逐只分析。',
  startScan: '开始扫描', pause: '暂停', resume: '继续', retry: '重试失败项', pauseHint: '当前请求结束后暂停', progress: '扫描进度', dataProgress: '行情同步', analysisProgress: 'Jev 分析', ready: '已完成', failed: '失败', skipped: '已跳过', pending: '待处理',
  running: '运行中', preparing: '准备中', pausing: '暂停中', paused: '已暂停', completed: '已完成', partial: '部分完成', data: '同步行情', analysis: '生成分析', noScans: '尚无扫描任务。', noHistory: '分析记录将保存在本机。',
  scanId: '任务', result: '结果', details: '详情', error: '暂时无法完成', retryHint: '请检查配置或稍后重试。', loading: '正在加载…', localResearch: '本地技术研究 · 仅完整日线', noDataService: '行情由用户自行获取',
  all: '全部', filters: '筛选', positionFree: '不依赖个人持仓', reportLanguage: '导出使用当前界面语言', onlyLatest: '盘中分析使用前一交易日及之前的数据。', noChart: '尚无可展示的完整 K 线。',
  technicalPreview: '当前为技术分析预览；配置 Jev 后可生成总判断。', locateEvidence: '在图中查看',
  positive: '偏多事实', negative: '偏空事实', neutral: '中性事实', candles: '根 K 线', noReferencePrices: '仅判断、适用周期与证据',
} as const

const en: Record<keyof typeof zh, string> = {
  title: 'A-share technical analysis', subtitle: 'Clarity after the close.', workbench: 'Workbench', scans: 'Market scans', history: 'History', settings: 'Settings',
  watchlist: 'Watchlist', addStock: 'Add a stock', searchPlaceholder: 'Search symbol or name', search: 'Search', emptyWatch: 'Start with one stock.', emptyWatchHint: 'Search and add a stock, or analyze a symbol directly.',
  analyze: 'Analyze', analyzing: 'Fetching data and analyzing…', batch: 'Analyze watchlist', marketScan: 'Scan the market', noSelection: 'Select a stock to explore its technical state.',
  emptyTitle: 'Read the structure behind price and volume.', emptyDescription: 'Eight dimensions. One traceable decision. Evaluate completed sessions and inspect the evidence on both sides.',
  enterSymbol: 'Enter a six-digit symbol', startAnalysis: 'Start analysis', configureJev: 'Configure Jev', local: 'Local workspace', daily: 'Completed sessions', provider: 'Data provider', model: 'Decision model', connected: 'Configured', notConfigured: 'Not configured',
  feature1: 'Eight analytical dimensions', feature1Text: 'Trend, momentum, volume, volatility and structure, with patterns, timeframes and relative strength.', feature2: 'Traceable evidence', feature2Text: 'Every observation is tied to indicators and dates. Supporting and opposing signals are shown together.', feature3: 'Your data. Your configuration.', feature3Text: 'Your environment retrieves prices from AKShare or Tushare. Jev uses your own API key.',
  buy: 'Buy', hold: 'Hold', sell: 'Sell', noDecision: 'No decision', horizon: 'Applicable horizon', sessions: 'trading sessions', next: 'Next', asOf: 'Data as of', source: 'Data source', rows: 'Historical daily bars', cached: 'Reused analysis', refresh: 'Refresh analysis',
  decision: 'Overall decision', support: 'Supporting evidence', oppose: 'Opposing evidence', context: 'Context', allEvidence: 'All evidence', noEvidence: 'No evidence of this type is available.',
  keyHint: 'Configure your Jev API key to generate a decision. Indicators and technical evidence remain available.',
  priceChart: 'Price & indicators', adjusted: 'Forward adjusted', day: 'Daily', week: 'Weekly', month: 'Monthly', completedOnly: 'Completed candles only', volume: 'Volume', indicator: 'Lower pane', overlay: 'Overlay',
  evidenceTab: 'Evidence', indicatorsTab: 'Indicators', qualityTab: 'Data notes', date: 'Date', value: 'Value', noValue: 'Unavailable', metrics: 'Indicators', unavailable: 'Missing information', noNotices: 'No additional data gaps were reported.',
  download: 'Export', open: 'Open', remove: 'Remove from watchlist', addWatch: 'Add to watchlist', close: 'Close', save: 'Save configuration', saving: 'Saving…', key: 'Jev API key', keyPlaceholder: 'Enter your TypeSafe API key', keySaved: 'Saved; leave blank to keep it',
  keyHelp: 'Credentials stay on your machine and are excluded from analysis results and exports.', sourceHelp: 'Public data needs no API key. Stock bars and benchmark indices have backup sources.', providerHelp: 'Applies immediately after saving. Provider caches are separate; past analyses keep their original sources.', tushareHelp: 'Use your own Tushare Pro token. Stock lists, calendars, adjustment factors and indices generally require 2,000 points; Shenwan daily indices require 5,000. Actual account permissions apply.', tokenPlaceholder: 'Enter your Tushare Pro token', modelHelp: 'Choose a model alias available to your TypeSafe account.',
  exchanges: 'Exchanges', excludeSpecial: 'Exclude ST / delisting stocks by default', liquidity: 'Minimum 20-day average turnover (CNY)', liquidityHelp: '0 disables the additional turnover filter. Suspensions and insufficient history are still excluded.',
  scope: 'Scan universe', fullMarket: 'All stocks on selected exchanges', watchScope: 'Watchlist', scanHint: 'Evaluate every eligible stock with Jev. The scan synchronizes historical data first, then analyzes each stock.',
  startScan: 'Start scan', pause: 'Pause', resume: 'Resume', retry: 'Retry failures', pauseHint: 'Pauses after the current request', progress: 'Scan progress', dataProgress: 'Data sync', analysisProgress: 'Jev analysis', ready: 'Completed', failed: 'Failed', skipped: 'Skipped', pending: 'Pending',
  running: 'Running', preparing: 'Preparing', pausing: 'Pausing', paused: 'Paused', completed: 'Completed', partial: 'Partially complete', data: 'Syncing data', analysis: 'Analyzing', noScans: 'No scans yet.', noHistory: 'Analysis history will be saved locally.',
  scanId: 'Job', result: 'Result', details: 'Details', error: 'Unable to complete', retryHint: 'Check configuration or try again later.', loading: 'Loading…', localResearch: 'Local technical research · Completed sessions', noDataService: 'User-supplied market access',
  all: 'All', filters: 'Filter', positionFree: 'Independent of personal holdings', reportLanguage: 'Exports use the current language', onlyLatest: 'Intraday requests use data through the previous trading session.', noChart: 'No completed candles are available.',
  technicalPreview: 'Technical preview. Configure Jev to generate an overall decision.', locateEvidence: 'Locate on chart',
  positive: 'Bullish fact', negative: 'Bearish fact', neutral: 'Neutral fact', candles: 'candles', noReferencePrices: 'Decision, horizon & evidence',
}

export type Key = keyof typeof zh
export const translate = (lang: Lang, key: Key): string => (lang === 'zh' ? zh : en)[key]
export const groups: Record<string, [string, string]> = { trend: ['趋势', 'Trend'], momentum: ['动量', 'Momentum'], volume: ['量价', 'Volume'], volatility: ['波动', 'Volatility'], structure: ['价格结构', 'Structure'], candles: ['K 线形态', 'Candlesticks'], multitimeframe: ['多周期', 'Timeframes'], relative: ['相对强弱', 'Relative strength'], summary: ['汇总', 'Aggregate'] }
export const groupName = (group: string, lang: Lang) => groups[group]?.[lang === 'en' ? 1 : 0] ?? group
