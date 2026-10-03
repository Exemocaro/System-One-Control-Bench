// src: src/system_one_control/players/local.py; src/system_one_control/players/remote.py; uv.lock; analysis/manifest.toml; docs/details.md
#set par(leading: 0.35em, spacing: 0.65em)
#set text(size: 8.5pt)

#figure(table(columns: (0.8fr, 1.55fr, 1.5fr), stroke: none, inset: 2pt, align: left,
  table.header([Model], [Model ID / host], [Precision and inference limits]),
  [Jev], [jev-1.13.0 / TypeSafe], [Remote precision unreported; highest option probability.],
  [Laya], [convaiinnovations/laya, typed-decisions / local], [Precision unrecorded; 8,192 request tokens, 48 per option.],
  [GLiClass], [knowledgator/gliclass-modern-large-v3.0 / local], [Precision unrecorded; 8,192 tokens, up to 128 labels.],
  [Qwen3.5-4B], [Qwen/Qwen3.5-4B / local], [bfloat16; thinking off; scored option numbers, no generated answer.],
  [Gemma 4 26B], [google/gemma-4-26b-a4b-it / OpenRouter, DeepInfra], [Remote precision unreported; reasoning off, 64 answer tokens.],
  [DeepSeek V4.1 Flash], [deepseek/deepseek-v4.1-flash / OpenRouter, DeepInfra], [Remote precision unreported; direct: 64 answer tokens; reasoning: 1,024 + 64 tokens.]),
  caption: [Evaluated model IDs and inference settings. Local checkpoint revisions were not recorded; software dependencies are locked in `uv.lock`.]) <tab:reproducibility>

Qwen3.5-4B and the local exam runs used an Acer Predator PHN16S-71 laptop: Intel Core Ultra 9 275HX (24 cores), 32 GB DDR5-6400, NVIDIA RTX 5070 Ti Laptop GPU (12 GB, driver 581.80), Windows 11. Laya and GLiClass game runs on 25–26 September used a consumer GPU; its exact hardware is not recorded here.

Laptop software: Python 3.11.9, CUDA 13.0, torch 2.14.0+cu130, transformers 5.17.0 and gliclass 0.1.20. Runs span 23 September–3 October 2026; result filenames in `analysis/manifest.toml` identify dates. Other-machine software versions and local precision, except Qwen3.5-4B, were not recorded here.

Latency measures the successful answering call alone, excluding retries, waits and model loading. Recorded USD costs sum provider-reported answering-call costs and are scaled per 100 games; earlier failed attempts have no recorded cost. Jev and local-model dollar costs are unavailable. Host/device differences prevent a controlled hardware comparison.
