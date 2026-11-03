/** Customer-facing facts about one model, from `GET /v1/agent-models/catalog` (one entry per model). No pricing. */
export type ModelDetails = {
  id: string
  name: string
  provider: string
  provider_label: string
  /** False when OpenRouter doesn't list the model; everything below is then empty. */
  listed: boolean
  description: string | null
  context_length: number | null
  max_output_tokens: number | null
  input_modalities: string[]
  output_modalities: string[]
  supports_tools: boolean
  supports_structured_output: boolean
  supports_reasoning: boolean
  supports_temperature: boolean
  supported_parameters: string[]
  knowledge_cutoff: string | null
  released_at: string | null
  retires_at: string | null
  is_moderated: boolean | null
}

/** 262144 → "262K", 1048576 → "1M". */
export const tokens = (count: number) => count >= 1_000_000 ? `${+(count / 1_000_000).toFixed(1)}M` : `${Math.round(count / 1000)}K`
