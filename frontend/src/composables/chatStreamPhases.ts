export const STREAM_PHASES = [
  'loading_evidence',
  'building_prompt',
  'generating',
  'post_processing',
] as const

export type StreamPhase = (typeof STREAM_PHASES)[number]

const PHASE_I18N_KEYS: Record<StreamPhase, string> = {
  loading_evidence: 'app.stream_loading_evidence',
  building_prompt: 'app.stream_building_prompt',
  generating: 'app.stream_generating',
  post_processing: 'app.stream_post_processing',
}

export function isStreamPhase(value: string): value is StreamPhase {
  return (STREAM_PHASES as readonly string[]).includes(value)
}

export function phaseI18nKey(phase: string): string {
  if (isStreamPhase(phase)) return PHASE_I18N_KEYS[phase]
  return 'app.in_progress'
}

export function phaseIndex(phase: string | null): number {
  if (!phase) return -1
  return STREAM_PHASES.indexOf(phase as StreamPhase)
}

export function isTimeoutError(message: string): boolean {
  return /timeout|timed out/i.test(message)
}
