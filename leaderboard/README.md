# Leaderboard

Core track, best everything progress first.

- **everything / map**: the core track conditions (compass rules, 100 puzzles each);
  `everything` is the full context.
- **won**: share of the 100 puzzles where the goal was reached before the move limit.
- **progress**: how close a game got to the goal at its closest point (1 for a win).
- **SPL**: fewest moves over moves used for a won game, 0 for a lost one.
- **[lo-hi]**: 95% bootstrap interval over puzzles (1,000 draws; the report uses 10,000, so
  the ends can differ by 0.01).
- **cost**: USD for one core run (200 games), as reported by the player; n/a means not reported.
- **latency**: median seconds per answer (the successful call alone).
- **kind**: baseline, chat model or decision model.

How to submit: [SUBMITTING.md](../SUBMITTING.md).

|player|org|kind|everything won|everything progress|everything SPL|map won|map progress|map SPL|cost|latency|notes|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Solver||baseline|1.00 [1.00-1.00]|1.00 [1.00-1.00]|1.00 [1.00-1.00]|1.00 [1.00-1.00]|1.00 [1.00-1.00]|1.00 [1.00-1.00]|0|0|Always plays a best move; the upper bound|
|[DeepSeek V4.1 Flash (reasoning)](https://openrouter.ai/deepseek/deepseek-v4.1-flash)|DeepSeek|chat|0.80 [0.72-0.88]|0.86 [0.80-0.92]|0.74 [0.66-0.81]|0.67 [0.58-0.76]|0.79 [0.72-0.85]|0.62 [0.53-0.71]|0.7121|6.84|deepseek/deepseek-v4.1-flash via OpenRouter (DeepInfra), reasoning capped at 1,024 tokens|
|[DeepSeek V4.1 Flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash)|DeepSeek|chat|0.60 [0.51-0.70]|0.72 [0.64-0.79]|0.54 [0.46-0.64]|0.39 [0.30-0.49]|0.55 [0.47-0.63]|0.35 [0.26-0.44]|0.0954|0.81|deepseek/deepseek-v4.1-flash via OpenRouter (DeepInfra), reasoning off|
|[Gemma 4 26B](https://huggingface.co/google/gemma-4-26b-a4b-it)|Google|chat|0.61 [0.52-0.70]|0.71 [0.64-0.79]|0.57 [0.48-0.66]|0.35 [0.26-0.45]|0.45 [0.37-0.54]|0.32 [0.23-0.41]|0.119|0.66|google/gemma-4-26b-a4b-it via OpenRouter (DeepInfra), reasoning off|
|[Jev](https://docs.typesafe.ai)|TypeSafe|decision|0.57 [0.47-0.67]|0.68 [0.60-0.76]|0.54 [0.44-0.64]|0.32 [0.23-0.41]|0.43 [0.35-0.51]|0.32 [0.23-0.41]|n/a|0.5|jev-1.13.0 through its API; cost not reported|
|[Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B)|Alibaba (Qwen)|chat|0.45 [0.35-0.55]|0.66 [0.59-0.73]|0.39 [0.30-0.48]|0.14 [0.08-0.22]|0.34 [0.27-0.41]|0.12 [0.06-0.19]|n/a|0.21|Qwen/Qwen3.5-4B in bfloat16, run locally, thinking off, scored on option-number probabilities|
|Greedy-walls||baseline|0.37 [0.28-0.48]|0.47 [0.39-0.56]|0.37 [0.28-0.48]|0.37 [0.28-0.48]|0.47 [0.39-0.56]|0.37 [0.28-0.48]|0|0|Straight at the next target, never into a wall|
|Greedy||baseline|0.28 [0.19-0.37]|0.36 [0.28-0.44]|0.28 [0.19-0.37]|0.28 [0.19-0.37]|0.36 [0.28-0.44]|0.28 [0.19-0.37]|0|0|Straight at the next target, ignoring walls|
|[Laya](https://huggingface.co/convaiinnovations/laya)|ConvAI Innovations|decision|0.12 [0.06-0.19]|0.26 [0.21-0.33]|0.10 [0.05-0.17]|0.02 [0.00-0.05]|0.10 [0.07-0.15]|0.02 [0.00-0.05]|n/a|1.64|convaiinnovations/laya, typed-decisions, run locally on a CPU|
|Random||baseline|0.04 [0.01-0.08]|0.25 [0.20-0.30]|0.03 [0.01-0.07]|0.04 [0.01-0.08]|0.25 [0.20-0.30]|0.03 [0.01-0.07]|0|0|A random offered move|
|[GLiClass](https://huggingface.co/knowledgator/gliclass-modern-large-v3.0)|Knowledgator|decision|0.13 [0.07-0.20]|0.22 [0.15-0.29]|0.13 [0.07-0.20]|0.03 [0.00-0.07]|0.10 [0.07-0.15]|0.03 [0.00-0.07]|n/a|1.5|knowledgator/gliclass-modern-large-v3.0, run locally on a CPU|
