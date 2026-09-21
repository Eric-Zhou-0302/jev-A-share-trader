export const MAX_BATCH_SIZE = 50

export function parseSymbols(input: string) {
  const tokens = input.split(/[\s,，;；、]+/).filter(Boolean)
  const symbols = new Set<string>()
  const invalid: string[] = []
  let duplicates = 0
  for (const token of tokens) {
    const match = /^(?:(SH|SZ|BJ))?(\d{6})(?:\.(SH|SZ|BJ))?$/.exec(token.toUpperCase())
    const code = match?.[2] ?? ''
    const market = /^(600|601|603|605|688|689)/.test(code) ? 'SH' : /^(000|001|002|003|300|301)/.test(code) ? 'SZ' : /^(43|83|87|88|92)/.test(code) ? 'BJ' : ''
    if (!match || !market || (match[1] && match[1] !== market) || (match[3] && match[3] !== market)) {
      invalid.push(token)
      continue
    }
    const symbol = `${code}.${market}`
    if (symbols.has(symbol)) duplicates += 1
    symbols.add(symbol)
  }
  return { symbols: [...symbols], invalid, duplicates }
}
