// src: src/system_one_control/players/local.py; src/system_one_control/players/remote.py; uv.lock; analysis/manifest.toml; docs/details.md
#set par(leading: 0.35em, spacing: 0.65em)
#set text(size: 8.5pt)

#figure(table(columns: (0.8fr, 1.55fr, 1.5fr), stroke: none, inset: 2pt, align: left,
  table.header([Model], [Model ID / host], [Precision and inference limits]),
  [Jev], [jev-1.13.0 / TypeSafe], [Remote precision unreported; highest option probability.],
  [Laya], [convaiinnovations/laya, subfolder typed-decisions (also published as convaiinnovations/laya-typed-decisions @layacard) / local], [Precision unrecorded; 8,192 request tokens, 48 per option.],
  [GLiClass], [knowledgator/gliclass-modern-large-v3.0 / local], [Precision unrecorded; 8,192 tokens, up to 128 labels.],
  [Qwen3.5-4B], [Qwen/Qwen3.5-4B / local], [bfloat16; thinking off; scored option numbers, no generated answer.],
  [Gemma 4 26B], [google/gemma-4-26b-a4b-it / OpenRouter, DeepInfra], [Remote precision unreported; reasoning off, 64 answer tokens.],
  [DeepSeek V4.1 Flash], [deepseek/deepseek-v4.1-flash / OpenRouter, DeepInfra], [Remote precision unreported; direct: 64 answer tokens; reasoning: 1,024 + 64 tokens.]),
  caption: [Evaluated model IDs and inference settings. Revisions cached on the laptop: Laya `55cf4c4`, GLiClass `668dd0d`, Qwen3.5-4B `851bf6e`. Software dependencies are locked in `uv.lock`.]) <tab:reproducibility>

The Laya and GLiClass compass games on 25 September ran on the CPU of a second computer, without a GPU; its exact model is not recorded. Every other local run (Laya and GLiClass sequence-rule games on 26 September and later, Qwen3.5-4B, and all exam runs) used an Acer Predator PHN16S-71 laptop: Intel Core Ultra 9 275HX (24 cores), 32 GB DDR5-6400, NVIDIA RTX 5070 Ti Laptop GPU (12 GB, driver 581.80), Windows 11.

Laptop software: Python 3.11.9, CUDA 13.0, torch 2.14.0+cu130, transformers 5.17.0 and gliclass 0.1.20. Runs span 23 September–3 October 2026; result filenames in `analysis/manifest.toml` identify dates. Other-machine software versions and local precision, except Qwen3.5-4B, were not recorded here.

Latency measures the successful answering call alone, excluding retries, waits and model loading. Recorded USD costs sum provider-reported answering-call costs and are scaled per 100 games; earlier failed attempts have no recorded cost. Jev and local-model dollar costs are unavailable. Host/device differences prevent a controlled hardware comparison.

Chat requests set neither temperature nor `top_p`; they use provider defaults. Direct answers allow 64 tokens. DeepSeek V4.1 Flash (reasoning), artifact ID `deepseek-v4.1-flash-think`, allows 1,024 reasoning tokens plus 64 answer tokens. OpenRouter retries refused calls four times, after 5, 15, 30 and 60 seconds. Its timeout is 120 seconds for direct answers and 600 seconds for reasoning. Jev retries refused calls twice, after one and two seconds, but does not retry a 120-second timeout.

Laya receives the full state as the first argument of `system_one`. The controller expands the total and question/option token budgets to fit the request. Option IDs are omitted because Laya would print them within each option's 48-token allowance. GLiClass uses a multi-label pipeline, with each independent score between 0 and 1 before normalisation. Qwen3.5-4B scores allowed option numbers in its chat template with thinking off and generates no answer.

The exam uses seed 0, with five items per puzzle or four at level 1. Item counts are 100 start, 95 on-route, 144 off-route, 88 after-blocked and 68 late-route (after the key where present). Missing kinds are filled with labelled off-route or after-blocked items, sometimes reusing a board. Random selects a fixed shuffled slot; chance optimality is 0.27.

Replaying every recorded game with the code current at each run and with the released code gives byte-identical requests: state, question and every option. The exception is the documented up-to subgoal question in the five subgoal conditions (@app:history). Rerunning GLiClass, Laya and Qwen3.5-4B at 529 recorded positions (176, 124 and 229, respectively) reproduced their probabilities exactly. This includes Laya with its newer Hugging Face revision `7b928d8`.

Jev returned different probabilities for identical requests at ten positions, with a spread up to 0.14 across three calls. On replay it chose the same move at 91 of 92 positions. DeepSeek V4.1 Flash gave up to four different answers in five identical calls at provider defaults. These checks show that reruns of Jev or the chat models would play different games. The reported results are single trajectories. Puzzle-bootstrap intervals describe variation across the evaluated puzzle collection, not repeated calls. Zero errors describes the retained records after errored games were replayed with `--resume`; transient failures occurred.

This report describes release v1.0.0 of the repository (code, puzzles, results and `analysis/manifest.toml`).
