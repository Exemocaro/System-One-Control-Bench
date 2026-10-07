#import "../lib.typ": todo

= Conclusion

System-One Control Bench tests models on single decisions and on whole games, in a world where every optimal move is known. With full context under compass rules, the non-generative decision model Jev achieves a success rate of 57%, compared with 61% for Gemma 4 26B and 60% for DeepSeek V4.1 Flash without reasoning; the paired comparisons do not establish a difference. Full context raises Jev's success rate from 32% with the map only to 57%. Laya and GLiClass play near chance level with the map only and remain weak with full context. DeepSeek V4.1 Flash (reasoning) plays best, but each answer takes about 7 seconds. For every model, answering single positions well does not guarantee reaching the goal: Jev picks an optimal move in 90% of the exam positions but wins 57% of its games. These results hold for these puzzles, conditions and settings.
// src: analysis/out/exam.md; analysis/out/main.md; analysis/out/cost.md
