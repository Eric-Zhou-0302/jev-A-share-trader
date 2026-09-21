export type Lang = 'zh' | 'en'
export type Action = 'buy' | 'hold' | 'sell'
export interface Stock { symbol: string; name: string; market?: string; board?: string }
export interface Notice { code: string; zh: string; en: string }
export interface Evidence { id: string; group: string; polarity: number; zh: string; en: string; date: string; side: 'support' | 'oppose' | 'context' }
export interface Point { time: string; value: number }
export interface Bar { date: string; open: number; high: number; low: number; close: number; volume: number }
export interface Metric { key: string; group: string; label: string; value: number | null; unit: string }
export interface Analysis {
  id: string; symbol: string; name: string; as_of: string; source: string; status: string;
  action: Action | null; horizon: string | null; rows: number; created_at: string; cached: boolean;
  evidence: Evidence[]; metrics: Metric[]; bars: Bar[]; charts: Record<string, Point[] | Bar[]>; notices: Notice[]; groups_available: string[];
}
export type Summary = Pick<Analysis, 'id' | 'symbol' | 'name' | 'as_of' | 'status' | 'action' | 'horizon' | 'created_at'>
export interface Settings { model: string; provider: string; jev_configured: boolean; tushare_configured: boolean; markets: string[]; exclude_special: boolean; min_amount: number; language: Lang }
export interface JobItem { stock: Stock; status: string; data_status: string; analysis_id: string | null; analysis_deleted?: boolean; action?: Action; horizon?: string; error?: Notice | null }
export interface Job { id: string; scope: string; status: string; phase: string; total: number; downloaded: number; completed: number; failed: number; skipped: number; remaining: number; as_of: string | null; current_symbol?: string | null; created?: number; error?: Notice | null; items?: JobItem[] }
