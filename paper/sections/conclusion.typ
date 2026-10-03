#import "../lib.typ": todo

= Conclusion

Capped reasoning gives DeepSeek V4.1 Flash the highest observed completion rate among the models. Jev's full-context rate is similar to Gemma and DeepSeek without reasoning within overlapping intervals. Laya and GLiClass remain near random with the map alone. Adding local descriptions, history or simulated outcomes to the map alone improves Jev's completion; the subgoal does not pass the corrected test. Longer sequences have mixed effects. For Jev, moves with chosen probability $p >= 0.9$ are more often optimal (0.74 versus 0.42 below; H7 in @tab:hyp), though the reliability curve is not monotone. The shared-position exam finds similar full-context optimality for Jev and Gemma, while capped reasoning remains strongest.
// src: analysis/out/exam.md; analysis/out/main.md; analysis/out/components.md; analysis/out/action_spaces.md; analysis/out/calibration.md; analysis/out/hypotheses.md; analysis/out/coverage.md
