/**
 * 轻量 Markdown 渲染：先 HTML 转义，再只支持标题/列表/粗体/行内代码/代码块/安全链接。
 * 不引入第三方依赖，避免 Wiki 内容执行任意 HTML。
 */

export function escapeHtml(text: string): string {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function safeLink(href: string, label: string): string {
  const url = href.trim()
  if (!/^https?:\/\//i.test(url)) return label
  return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
}

export function renderMarkdown(markdown: string): string {
  let text = escapeHtml(markdown)
  const codeBlocks: string[] = []
  text = text.replace(/```([\s\S]*?)```/g, (_match, code: string) => {
    const index = codeBlocks.length
    codeBlocks.push(`<pre class="wiki-code"><code>${code}</code></pre>`)
    return `\u0000CODE${index}\u0000`
  })
  text = text.replace(/^### (.*)$/gm, '<h4>$1</h4>')
  text = text.replace(/^## (.*)$/gm, '<h3>$1</h3>')
  text = text.replace(/^# (.*)$/gm, '<h2>$1</h2>')
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_m, label, href) =>
    safeLink(href, label),
  )
  text = text.replace(/^(?:- |\* )(.*)$/gm, '<li>$1</li>')
  text = text.replace(/(?:<li>.*<\/li>\n?)+/g, (block) => `<ul>${block}</ul>`)
  text = text.replace(/\n{2,}/g, '</p><p>')
  text = text.replace(/\n/g, '<br/>')
  text = `<p>${text}</p>`
  codeBlocks.forEach((block, index) => {
    text = text.replace(`\u0000CODE${index}\u0000`, block)
  })
  return text
}
