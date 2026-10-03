#import "../lib.typ": todo

= Related work

Jev has been evaluated as a legal-move selector in chess @saplin2026jev and compared with Laya and a local Qwen3 decision model @chopra2026gist. Laya's evaluated checkpoint specializes in four workflow domains and cautions about transfer @layacard. GLiClass performs zero-shot classification over supplied labels in a single forward pass @stepanov2025gliclass; treating option texts as labels lets us evaluate such a classifier as a sequential controller.
// src: paper/references.bib

PlanBench tests planning and reasoning about change in formal domains @valmeekam2022planbench. AgentBench covers eight interactive environments @liu2023agentbench, and BALROG evaluates agents across games of differing difficulty @paglieri2024balrog. We instead vary input components within one small environment to diagnose non-generative decision models. BabyAI @chevalier2019babyai and MiniGrid @chevalier2023minigrid provide related gridworld tasks; compass moves here separate map interpretation from orientation control.
// src: paper/references.bib; src/system_one_control/world.py

SayCan combines language-based skill selection with feasibility estimates @ahn2022saycan, while SayCanPay adds learned domain knowledge @hazra2024saycanpay. Our simulated outcomes are deterministic transitions supplied by environment code. Multiple-choice selection is sensitive to option identifiers and order @zheng2024selection, motivating seeded shuffling without assuming it removes bias. Calibration methods distinguish confidence from correctness @guo2017calibration; our target accepts any solver-optimal move, rather than a unique class label.
// src: paper/references.bib; src/system_one_control/prompts.py
