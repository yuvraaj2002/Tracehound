from transformers import pipeline

pipe = pipeline("text-generation", model="LiquidAI/LFM2.5-24B-A2B")
messages = [
    {"role": "user", "content": "Who are you?"},
]
pipe(messages)
