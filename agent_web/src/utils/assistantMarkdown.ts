import MarkdownIt from 'markdown-it'

// Only this parser's generated markup reaches v-html. Model-supplied HTML stays escaped.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true, typographer: false })
const defaultValidateLink = markdown.validateLink.bind(markdown)
markdown.validateLink = (url: string) => {
  const normalized = url.replace(/[\u0000-\u0020\u007f-\u009f]/g, '')
  return defaultValidateLink(url) && (/^(https?:|mailto:)/i.test(normalized) ||
    (!/^[a-z][a-z\d+.-]*:/i.test(normalized) && !normalized.startsWith('//')))
}
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return renderer.renderToken(tokens, index, options)
}
markdown.renderer.rules.table_open = () => '<div class="markdown-table-scroll" role="region" aria-label="数据表格" tabindex="0"><table>\n'
markdown.renderer.rules.table_close = () => '</table></div>\n'
// Render alt text without automatically requesting model-provided remote image URLs.
markdown.renderer.rules.image = (tokens, index) => `<span class="markdown-image-alt">${markdown.utils.escapeHtml(tokens[index].content || '图片')}</span>`

export function renderAssistantMarkdown(content: string): string {
  return markdown.render(content)
}
