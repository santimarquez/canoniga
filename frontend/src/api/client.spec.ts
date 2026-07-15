import { describe, expect, it } from 'vitest'
import { readNdjsonStream } from '@/api/client'

describe('readNdjsonStream', () => {
  it('parses NDJSON events until stop', async () => {
    const payload = [
      JSON.stringify({ type: 'status', phase: 'generating', message: 'Working' }),
      JSON.stringify({ type: 'chunk', delta: 'Hello' }),
      JSON.stringify({ type: 'final', answer: 'Hello', evidence_count: 1 }),
    ].join('\n')

    const encoder = new TextEncoder()
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(payload))
          controller.close()
        },
      }),
      { headers: { 'Content-Type': 'application/x-ndjson' } },
    )
    const events = []
    for await (const event of readNdjsonStream<{ type: string }>(response, (event) => {
      if (event.type === 'final') return 'stop'
    })) {
      events.push(event)
    }
    expect(events).toHaveLength(2)
    expect(events[1]).toMatchObject({ type: 'chunk', delta: 'Hello' })
  })
})
