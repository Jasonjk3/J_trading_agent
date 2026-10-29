import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'vite'
import { fileURLToPath } from 'node:url'

const result = await build({ configFile: false, logLevel: 'silent', build: { write: false, minify: false,
  lib: { entry: fileURLToPath(new URL('../src/utils/assistantMarkdown.ts', import.meta.url)), formats: ['es'], fileName: 'markdown' } } })
const code = (Array.isArray(result) ? result[0] : result).output.find(item => item.type === 'chunk').code
const { renderAssistantMarkdown: render } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('market response renders bold text and a horizontally scrollable semantic table', () => {
  const html = render('## ETH 行情\n\nOKX **ETH-USDT**，最新价 **2404.26 USDT**。\n\n| 时间 | 开 | 高 | 低 | 收 | 成交量(ETH) |\n|---|---:|---:|---:|---:|---:|\n| 13:38（进行中） | 2403.07 | 2404.36 | 2403.07 | 2404.26 | 0.92 |')
  assert.match(html, /<h2>ETH 行情<\/h2>/)
  assert.match(html, /<strong>ETH-USDT<\/strong>/)
  assert.match(html, /class="markdown-table-scroll" role="region" aria-label="数据表格" tabindex="0"/)
  assert.match(html, /<thead>[\s\S]*<th>时间<\/th>/)
  assert.match(html, /<tbody>[\s\S]*2404\.26/)
  assert.doesNotMatch(html, /\|---/)
})

test('headings, nested lists, quotes, line breaks and fenced code keep their structure', () => {
  const html = render('# 标题\n\n1. 第一项\n   - 子项\n2. 第二项\n\n> 风险提示\n\n第一行\n第二行\n\n`price`\n\n```python\nprint("<script>alert(1)</script>")\n```')
  for (const tag of ['h1', 'ol', 'ul', 'blockquote', 'pre']) assert.ok(html.includes(`<${tag}>`), tag)
  assert.match(html, /<br>/)
  assert.match(html, /<code>price<\/code>/)
  assert.match(html, /<code class="language-python">/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})

test('model HTML remains text and remote image markup cannot issue requests', () => {
  const html = render('<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n<iframe src="https://example.com"></iframe>\n\n![说明](https://example.com/private-pixel.png)')
  assert.doesNotMatch(html, /<(script|img|iframe)\b/i)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /class="markdown-image-alt">说明<\/span>/)
  assert.doesNotMatch(html, /src="https:\/\/example.com\/private-pixel/)
})

test('unsafe URL schemes are rejected and valid links protect the original tab', () => {
  for (const url of ['javascript:alert%281%29', 'jav&#x61;script:alert%281%29', 'vbscript:msgbox%281%29', 'data:text/html,unsafe', 'data:image/png;base64,AAAA', 'file:///etc/passwd']) {
    assert.doesNotMatch(render(`[点击](${url})`), /<a\b/, url)
  }
  const html = render('[官方文档](https://example.com/docs?q=1&x=2 "文档")')
  assert.match(html, /href="https:\/\/example.com\/docs\?q=1&amp;x=2"/)
  assert.match(html, /target="_blank"/)
  assert.match(html, /rel="noopener noreferrer"/)
})
