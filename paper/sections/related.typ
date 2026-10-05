#import "../lib.typ": todo

= Related work

Jev has been tested as a chess-move picker @saplin2026jev and compared with Laya and a local Qwen3 decision model @chopra2026gist. The Laya checkpoint we test was trained on four kinds of workflow task, and its model card warns that it may not transfer to others @layacard. GLiClass classifies a text against any list of labels in a single pass @stepanov2025gliclass; using the option texts as labels turns it into a player.
// src: paper/references.bib

PlanBench tests planning in formal domains, where answers can be checked exactly @valmeekam2022planbench. AgentBench @liu2023agentbench and BALROG @paglieri2024balrog evaluate agents across many environments and games. We instead use one small environment and vary what the model is told, to find out what these models need. BabyAI @chevalier2019babyai and MiniGrid @chevalier2023minigrid are related grid worlds. Their agents turn and move forward; our compass moves need no sense of facing, so the task is about reading the map.
// src: paper/references.bib; src/system_one_control/world.py

SayCan combines a language model's choice of skill with an estimate of whether the skill can succeed @ahn2022saycan, and SayCanPay adds learned knowledge of the domain @hazra2024saycanpay. Our move outcomes are simpler: the environment's own code writes what each move would do. Multiple-choice answers are known to depend on the order and labels of the options @zheng2024selection, which is why we shuffle them. Calibration measures whether stated confidence matches how often a model is right @guo2017calibration.
// src: paper/references.bib; src/system_one_control/prompts.py
