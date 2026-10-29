export interface RunEvent { id: string; type: string; data: Record<string, unknown> }

/** Incremental SSE parser: handles split CRLF, multiline JSON and comment heartbeats. */
export class EventParser {
  private buffer = ''
  private id = ''
  private type = 'message'
  private data: string[] = []
  constructor(private receive: (event: RunEvent) => void) {}
  push(chunk: string) {
    this.buffer += chunk
    let index: number
    while ((index = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, index).replace(/\r$/, '')
      this.buffer = this.buffer.slice(index + 1)
      if (!line) {
        if (this.data.length) this.receive({ id: this.id, type: this.type, data: JSON.parse(this.data.join('\n')) })
        this.type = 'message'; this.data = []
      } else if (!line.startsWith(':')) {
        const split = line.indexOf(':')
        const field = split < 0 ? line : line.slice(0, split)
        const value = split < 0 ? '' : line.slice(split + 1).replace(/^ /, '')
        if (field === 'id' && !value.includes('\0')) this.id = value
        if (field === 'event') this.type = value
        if (field === 'data') this.data.push(value)
      }
    }
  }
}
