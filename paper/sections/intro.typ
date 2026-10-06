#import "../lib.typ": todo

= Introduction

AI models are increasingly asked to act step by step: choose an action, see what happens, choose the next. A model can choose well when shown a single situation and still fail when its own choices decide what it sees next. We test this in a small grid world where the best moves are known exactly.

We focus on *non-generative decision models*. Such a model does not write an answer: it receives a description of the situation, a question and a list of options, and returns a probability for each option; the program then plays the most likely one. Jev, from TypeSafe, is one such model. It has been tested as a chess player @saplin2026jev and as a controller for phone apps and web browsers @mobilejev @jevultrafast. We also test two open models that return probabilities: Laya's Typed-Decisions model, which was built for the same kind of request, and GLiClass, a classifier that can score any list of labels. We compare them with chat models, which normally write their answers, and with simple baselines. The benchmark is called System-One Control Bench after "System 1", the fast, automatic kind of thinking in which an answer comes directly: these models choose an action without writing out any reasoning first.
// src: paper/references.bib; README.md; src/system_one_control/players/local.py

In every puzzle the map holds all the information needed to reach the goal. We change two things: what extra descriptions the model gets, and how many steps one move contains. Five questions guide the report:

+ *RQ1:* How often do models reach the goal?
+ *RQ2:* Which extra information about the puzzle helps?
+ *RQ3:* Do good answers on fixed positions translate into won games?
+ *RQ4:* What changes when one move contains several steps?
+ *RQ5:* What do the returned probabilities tell us, and what do the models cost?

All puzzles, the solver, every request and every game record are public, so every result can be checked and recomputed.
// src: README.md; analysis/README.md
