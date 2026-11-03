import config from '../../../src/tracehound/resources/config.json'

/** The backend's model config (src/tracehound/resources/config.json) is the single source of truth. */
export type ConfigProvider = { id: string, label: string, models: string[] }

/** Logos are Simple Icons (CC0), tinted with CSS. Providers without one show a monogram. */
const logos: Record<string, string> = { nvidia: '/providers/nvidia.svg', google: '/providers/google.svg' }

export const gateway = config.gateway
export const defaultChoice = config.default
export const configProviders: ConfigProvider[] = config.providers

/** A model id without its provider prefix and `:free` suffix, e.g. "nemotron-3.5-lightning". */
export const modelName = (id: string) => id.split('/').slice(1).join('/').replace(/:free$/, '')

export const modelProviders = configProviders.map((provider) => ({
  id: provider.id,
  name: provider.label,
  logo: logos[provider.id] ?? null,
  /** Distinct display names: a model offered with and without a `:free` suffix is shown once. */
  models: [...new Set(provider.models.map(modelName))],
}))

export type ModelProvider = (typeof modelProviders)[number]

/** Display names and facts for each model, keyed by its id without prefix or `:free`. Tags come from the model's own name. */
const info: Record<string, { name: string, tags: string[] }> = {
  'nemotron-3-ultra-550b-a55b': { name: 'Nemotron 3 Ultra', tags: ['550B parameters', '55B active'] },
  'nemotron-3.5-super-vl': { name: 'Nemotron 3.5 Super VL', tags: ['Vision-language'] },
  'nemotron-3.5-lightning': { name: 'Nemotron 3.5 Lightning', tags: ['Nemotron 3.5'] },
  'nemotron-3-nano-omni-30b-a3b-reasoning': { name: 'Nemotron 3 Nano Omni', tags: ['30B parameters', '3B active', 'Reasoning'] },
  'nemotron-3.5-content-safety': { name: 'Nemotron 3.5 Content Safety', tags: ['Content safety'] },
  'llama-nemotron-rerank-vl-1b-v2': { name: 'Llama Nemotron Rerank VL', tags: ['1B parameters', 'Reranking', 'Vision-language'] },
  'dots-3-note-preview': { name: 'dots 3 Note', tags: ['Preview'] },
  'inkling': { name: 'Inkling', tags: ['Thinking Machines'] },
  'inkling-small': { name: 'Inkling Small', tags: ['Small'] },
  'north-mini-code': { name: 'North Mini Code', tags: ['Code', 'Mini'] },
  'xing4.0-29b-a4b': { name: 'Xing 4.0', tags: ['29B parameters', '4B active'] },
  'flint-v1.0': { name: 'Flint v1.0', tags: ['Version 1.0'] },
  'span-01-lite': { name: 'Span 01 Lite', tags: ['Lite'] },
  'lfm-2.5-2.6b': { name: 'LFM 2.5', tags: ['2.6B parameters'] },
  'gemma-4-26b-a4b-it': { name: 'Gemma 4 26B', tags: ['26B parameters', '4B active', 'Instruction-tuned'] },
}

/** A model's display name and tags, from the key used in `modelProviders[].models`. */
export const describeModel = (key: string) => info[key] ?? { name: key, tags: [] }

export const providerLogo = (id: string) => logos[id] ?? null
