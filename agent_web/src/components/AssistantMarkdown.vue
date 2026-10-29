<template>
  <div class="markdown-answer" :class="{ 'is-error': error }" @click="onLinkClick" v-html="html" />
  <p v-if="downloadError" role="alert" class="download-error">{{ downloadError }}</p>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { renderAssistantMarkdown } from '@/utils/assistantMarkdown'
import { assistantApi } from '@/api/assistant'

const props = withDefaults(defineProps<{ content: string; error?: boolean }>(), { error: false })
const html = computed(() => renderAssistantMarkdown(props.content))
const downloadError = ref('')
async function onLinkClick(event: MouseEvent) {
  const target = event.target instanceof Element ? event.target.closest('a') : null
  const path = target?.getAttribute('href') || ''
  if (!/^\/v1\/backtest\/[A-Za-z0-9_-]{1,64}\/export$/.test(path)) return
  event.preventDefault()
  downloadError.value = ''
  try {
    const { blob, filename } = await assistantApi.report(path)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = filename
    document.body.appendChild(anchor); anchor.click(); anchor.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (exc) { downloadError.value = exc instanceof Error ? exc.message : '报告下载失败' }
}
</script>

<style scoped>
.markdown-answer { min-width: 0; font-size: 13px; line-height: 1.9; color: #5a6a83; overflow-wrap: anywhere; }
.markdown-answer.is-error { color: #b45309; }
.download-error { color: #b45309; font-size: 12px; }
.markdown-answer :deep(> :first-child) { margin-top: 0; }
.markdown-answer :deep(> :last-child) { margin-bottom: 0; }
.markdown-answer :deep(p) { margin: 0 0 14px; }
.markdown-answer :deep(h1), .markdown-answer :deep(h2), .markdown-answer :deep(h3),
.markdown-answer :deep(h4), .markdown-answer :deep(h5), .markdown-answer :deep(h6) {
  color: #172338; font-weight: 600; line-height: 1.5; margin: 24px 0 12px; letter-spacing: 0;
}
.markdown-answer :deep(h1) { font-size: 24px; }
.markdown-answer :deep(h2) { font-size: 21px; }
.markdown-answer :deep(h3) { font-size: 17px; }
.markdown-answer :deep(h4), .markdown-answer :deep(h5), .markdown-answer :deep(h6) { font-size: 14px; }
.markdown-answer :deep(strong) { font-weight: 650; color: #25344b; }
.markdown-answer :deep(ul), .markdown-answer :deep(ol) { margin: 0 0 16px; padding-left: 24px; }
.markdown-answer :deep(li) { padding-left: 3px; margin: 5px 0; }
.markdown-answer :deep(li > p) { margin-bottom: 6px; }
.markdown-answer :deep(li > ul), .markdown-answer :deep(li > ol) { margin-bottom: 6px; }
.markdown-answer :deep(blockquote) { margin: 16px 0; border-left: 3px solid #a8c3fa; padding: 8px 16px; background: #f7faff; color: #64748b; }
.markdown-answer :deep(blockquote > :last-child) { margin-bottom: 0; }
.markdown-answer :deep(a) { color: #2563eb; text-decoration: underline; text-underline-offset: 3px; }
.markdown-answer :deep(a:hover) { color: #1d4ed8; }
.markdown-answer :deep(code) { font-family: Consolas, 'SFMono-Regular', monospace; font-size: .93em; border-radius: 4px; padding: 2px 5px; background: #eef2f7; color: #334155; }
.markdown-answer :deep(pre) { max-width: 100%; overflow-x: auto; margin: 16px 0; padding: 16px; border: 1px solid #e3e9f2; border-radius: 9px; background: #f7f9fc; line-height: 1.65; tab-size: 4; }
.markdown-answer :deep(pre code) { display: block; background: transparent; border: 0; border-radius: 0; padding: 0; white-space: pre; overflow-wrap: normal; }
.markdown-answer :deep(.markdown-table-scroll) { max-width: 100%; overflow-x: auto; margin: 18px 0; border: 1px solid #dfe7f2; border-radius: 8px; }
.markdown-answer :deep(.markdown-table-scroll:focus-visible) { outline: 2px solid #2563eb; outline-offset: 2px; }
.markdown-answer :deep(table) { width: 100%; border-collapse: collapse; text-align: left; font-variant-numeric: tabular-nums; }
.markdown-answer :deep(th), .markdown-answer :deep(td) { padding: 10px 14px; border-bottom: 1px solid #e6ecf4; vertical-align: top; min-width: 90px; }
.markdown-answer :deep(th) { background: #f4f7fc; color: #334155; font-weight: 600; white-space: nowrap; }
.markdown-answer :deep(td) { white-space: nowrap; }
.markdown-answer :deep(tr:last-child td) { border-bottom: 0; }
.markdown-answer :deep(tbody tr:nth-child(even)) { background: #fbfcfe; }
.markdown-answer :deep(hr) { border: 0; border-top: 1px solid #e3e9f2; margin: 22px 0; }
.markdown-answer :deep(.markdown-image-alt) { color: #64748b; }
@media (max-width: 650px) {
  .markdown-answer :deep(th), .markdown-answer :deep(td) { padding: 8px 10px; }
  .markdown-answer :deep(pre) { padding: 12px; }
}
</style>
