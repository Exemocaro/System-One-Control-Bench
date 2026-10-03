#import "../lib.typ": todo

= Evaluation protocol <sec:protocol>

== Models and baselines

Random chooses uniformly from the offered moves. Greedy moves toward the next target, and greedy-walls also avoids walls. The solver always chooses an optimal move and provides a ceiling. The greedy baselines use compass moves only. Each model receives the request without direct access to the environment or solver.
// src: README.md; src/system_one_control/players.py

Jev (`jev-1.13.0`) chooses the option with the highest returned probability. GLiClass (`modern-large-v3.0`) treats the state as classification text, the question as the task, and the option texts as labels. Its scores are normalized to sum to one. Qwen3.5-4B does not write an answer: the controller scores the digits of each option number in its chat template and selects the most likely one.
// src: src/system_one_control/local_players.py; players.py

Laya receives the full state as the first argument of `system_one`, together with the question and option texts. Only the option IDs are omitted, because Laya would print them within each option's 48-token allowance. The controller expands the token limits to fit the full request. It rejects an option above 48 tokens or a request above 8,192 tokens instead of truncating it. The evaluated checkpoint was trained for four workflow domains and warns about use outside them and large option sets @layacard. Our results concern this checkpoint's transfer to navigation under these input limits.
// src: src/system_one_control/local_players.py; Laya model card

Gemma and DeepSeek use OpenRouter with DeepInfra as the fixed host. They return an option ID through a JSON schema. Direct answers have a 64-token limit. DeepSeek's reasoning configuration allows 1,024 reasoning tokens plus 64 answer tokens and is evaluated under compass moves. Jev retries refused calls twice but does not retry a 120-second timeout. A missing, invalid or capped answer ends the game as an error and counts as a loss. Option order is shuffled using a seed based on the puzzle and move number. Each saved game provides one trajectory. Prompt development preceded puzzle generation; @app:history gives the chronology and the later question correction.
// src: src/system_one_control/llm_players.py; players.py; docs/DECISIONS.md; analysis/manifest.toml

== Metrics and statistics

Won rate is the share of games reaching the goal within the move limit, which is twice the solver's fewest moves. Progress is one minus the closest distance reached divided by the starting distance. It gives credit for approaching the goal even if the game later ends farther away. Final-state progress uses the ending position and can be negative. SPL is zero for a loss; for a win, it divides the fewest moves by the larger of that number and the moves used @anderson2018evaluation. Under sequence rules, distance and level count compass steps, while SPL and the move limit count model decisions. A blocked move leaves the board unchanged. Optimality accepts any move tied for the solver's best distance.
// src: analysis/README.md; src/system_one_control/solver.py; rules.py

Intervals are 95% percentile-bootstrap intervals over puzzles, with 10,000 resamples. Component comparisons pair the same puzzles. McNemar's exact test compares whether each game was won, and Holm correction covers the eight component contrasts for each model. Calibration pools all ten compass conditions. Ten-bin ECE and binary Brier score compare the chosen-option probability with whether that move was optimal @guo2017calibration. Accepting several tied best moves is different from validating a probability distribution over alternative moves. Every evaluated model/input has 100 games.
// src: analysis/README.md; analysis/out/components.md; analysis/out/calibration.md; analysis/out/coverage.md

The planned fixed-state evaluation will use positions selected in advance across levels. They will include positions on shortest routes, just off them, beside walls, and before and after key collection. Every model will answer the same compass questions once with the map alone and once with full context. This will compare decisions at the same positions, rather than positions selected by each model's earlier moves.
// src: fixed-state evaluation protocol
