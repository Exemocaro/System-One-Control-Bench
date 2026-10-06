#import "../lib.typ": todo
// src: src/system_one_control/players/local.py; src/system_one_control/players/remote.py; uv.lock; analysis/manifest.toml; docs/details.md
#set par(leading: 0.35em, spacing: 0.65em)
#set text(size: 8.5pt)

#figure(table(columns: (0.8fr, 1.55fr, 1.5fr), stroke: none, inset: 2pt, align: left,
  table.header([Model], [Model ID / where it ran], [Precision and limits]),
  [Jev], [jev-1.13.0 / TypeSafe], [Precision not reported.],
  [Laya], [convaiinnovations/laya, subfolder typed-decisions (also published as convaiinnovations/laya-typed-decisions @layacard) / local], [Precision not recorded; reads up to 8,192 tokens, 48 per option.],
  [GLiClass], [knowledgator/gliclass-modern-large-v3.0 / local], [Precision not recorded; reads up to 8,192 tokens and 128 labels.],
  [Qwen3.5-4B], [Qwen/Qwen3.5-4B / local], [bfloat16; reasoning off; writes nothing.],
  [Gemma 4 26B], [google/gemma-4-26b-a4b-it / OpenRouter, DeepInfra], [Precision not reported; reasoning off; answer up to 64 tokens.],
  [DeepSeek V4.1 Flash], [deepseek/deepseek-v4.1-flash / OpenRouter, DeepInfra], [Precision not reported; answer up to 64 tokens, plus up to 1,024 reasoning tokens with reasoning.]),
  caption: [Model IDs and settings. Model versions on the laptop: Laya `55cf4c4`, GLiClass `668dd0d`, Qwen3.5-4B `851bf6e`. Software versions are locked in the repository's `uv.lock`.]) <tab:reproducibility>

*Hardware.* The Laya and GLiClass compass games (25 September 2026) ran on the CPU of a second computer, without a GPU; its exact model was not recorded. Every other local run (the Laya and GLiClass sequence-rule games from 26 September on, all Qwen3.5-4B games, and all exam runs) used an Acer Predator PHN16S-71 laptop: Intel Core Ultra 9 275HX (24 cores), 32 GB of memory, NVIDIA RTX 5070 Ti Laptop GPU (12 GB), Windows 11, Python 3.11.9, CUDA 13.0, torch 2.14.0, transformers 5.17.0 and gliclass 0.1.20. The runs took place between 23 September and 6 October 2026; the result file names in `analysis/manifest.toml` give the dates.

*Calls.* Chat requests set neither temperature nor `top_p`, so the provider's defaults apply. DeepSeek V4.1 Flash with reasoning is called `deepseek-v4.1-flash-think` in the repository. A refused OpenRouter call is retried up to four times, after 5, 15, 30 and 60 seconds; a call times out after 120 seconds without reasoning and 600 with it. A refused Jev call is retried twice, after one and two seconds; a Jev call times out after 120 seconds and is not retried.

*Time and cost.* Times count only the successful call, without retries, waiting or model loading. Costs add up the provider-reported cost of each successful call; failed earlier attempts have no recorded cost. Different hosts and devices mean the times are not a controlled comparison.

*Local models.* Laya gets the full state as the first argument of its `system_one` call, and the program raises Laya's overall token limits as far as each request needs. An option longer than Laya's fixed 48 tokens would be refused rather than cut; none was. GLiClass gives each option an independent score between 0 and 1, which we scale to sum to 1. Qwen3.5-4B reads the chat with reasoning off, followed by the start of the answer, and we read the probability of each option number from it.

*Exam.* The exam positions were drawn once, with seed 0: 100 start, 95 on-route, 144 off-route, 88 after-blocked and 68 late. Where a kind of position cannot be made for a puzzle (for example, an after-blocked position in a puzzle whose route never passes a wall), an extra off-route or after-blocked position takes its place, sometimes on a board already used. Random always picks the option in one fixed place in the shuffled list, which is itself a random pick. Choosing uniformly at random would be optimal on 27% of these positions; Random scored 30%.
// src: exam/items.jsonl (mean over positions of best moves / options); analysis/out/exam.md

*One question changed.* On 26 September the subgoal question for the up-to rules was reworded to ask for the way that takes the fewest turns (moves). Every game that used the old wording was replayed by every player, and only the replays are used here.

*Replay checks.* Rebuilding every request from the recorded games, both with the code of the day and with the released code, gives byte-identical states, questions and options, apart from that one reworded question. Asking GLiClass, Laya and Qwen3.5-4B again at 529 recorded positions (176, 124 and 229) gave exactly the same probabilities, including with Laya's newer version `7b928d8`. Qwen3.5-4B's games under the four sequence rules were also checked this way, at 169 (`two-moves`), 169 (`up-to-two-moves`), 148 (`three-moves`) and 151 (`up-to-three-moves`) positions, with the same result. Jev, asked three times at ten positions, gave probabilities that differed by up to 0.14, and replayed at 92 positions it chose the same move at 91. DeepSeek V4.1 Flash gave up to four different answers in five identical calls. So a rerun of Jev or DeepSeek V4.1 Flash, and probably of Gemma 4 26B and DeepSeek V4.1 Flash (reasoning), would play different games, and the results here are one game per puzzle.
// src: scripts/replay_check.py (GLiClass, Laya, Qwen3.5-4B; the sequence-rule counts come from `qwen3.5-4b <file> all 40 5`); the Jev and DeepSeek V4.1 Flash checks were one-off calls made during the study, not kept in the repository

This report describes release v1.0.0 of the repository.
