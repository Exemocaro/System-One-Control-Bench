"""Write result prose and hypotheses only from the current analysis tables."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "sections"


def read(name):
    with (ROOT / "analysis" / "out" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(name, body):
    (OUT / f"{name}.typ").write_text('#import "../lib.typ": todo\n\n' + body, encoding="utf-8")


def percent(value):
    return f"{100 * float(value):.0f}%"


def interval(row, field, percentage=False):
    vals = [row[field + suffix] for suffix in ("", " low", " high")]
    fmt = (lambda x: f"{100 * float(x):.0f}") if percentage else (lambda x: f"{float(x):.2f}")
    return f"{fmt(vals[0])}{'%' if percentage else ''} [{fmt(vals[1])}, {fmt(vals[2])}]"


def sync_results():
    main = {(r["Model"], r["Input"]): r for r in read("main")}
    components = {(r["Model"], r["Component"], r["Direction"]): r for r in read("components")}
    spaces = {(r["Model"], r["Action space (options)"], r["Input"]): r for r in read("action_spaces")}
    calibration = {r["Model"]: r for r in read("calibration")}
    cost = {r["Model"]: r for r in read("cost")}
    reason = main[("DeepSeek V4.1 Flash (reasoning)", "full context")]
    reason_map = main[("DeepSeek V4.1 Flash (reasoning)", "map only")]
    jev = main[("Jev", "full context")]
    jev_map = main[("Jev", "map only")]
    sim = components[("Jev", "simulated action outcomes", "added to map only")]
    history = components[("Jev", "interaction history", "added to map only")]
    history_full = components[("Jev", "interaction history", "removed from full context")]
    sim_full = components[("Jev", "simulated action outcomes", "removed from full context")]
    levels = [r for r in read("levels") if r["Model"] == "Jev" and r["Input"] == "full context" and r["Level"] in ("12", "15", "20")]
    jc, lc, qc = (calibration[x] for x in ("Jev", "Laya", "Qwen3.5 4B"))

    write("abstract", f'''Non-generative decision models assign probabilities to supplied options without writing an answer. System-One Control Bench tests whether these decisions can guide navigation across 100 symbolic gridworld puzzles, ten input conditions and five action spaces. "System-One" refers to fast decisions without deliberate reasoning, after the System 1 / System 2 distinction; Laya calls its decision interface `system_one`. An exact solver identifies every optimal move, including ties. DeepSeek V4.1 Flash with capped reasoning has the highest completion rate among the models: it wins {percent(reason['Won rate'])} of full-context games. Jev wins {percent(jev['Won rate'])}, similar to Gemma and DeepSeek without reasoning within overlapping intervals. Supplying simulated outcomes improves Jev's navigation, but larger sets of sequence moves do not consistently help. Laya and GLiClass stay near random with the map alone. A planned evaluation on shared positions will compare models on the same decisions.
// src: analysis/out/main.md; analysis/out/components.md; analysis/out/action_spaces.md; analysis/out/coverage.md
''')

    write("results", f'''= Results <sec:results>

== Completion and efficiency

#include "main_table.typ"

DeepSeek V4.1 Flash with capped reasoning wins substantially more games than any other model. Its won rate is {interval(reason, 'Won rate', True)} with full context and {interval(reason_map, 'Won rate', True)} with the map alone. Each estimate uses {reason['Games']} games. All ten reasoning conditions have been evaluated, with no recorded errors.
// src: analysis/out/main.md; analysis/out/coverage.md

Jev wins {percent(jev_map['Won rate'])} with the map alone, below the wall-aware greedy baseline's observed 37% and above random's 4%. With full context, Jev, Gemma and DeepSeek without reasoning win 57%, 61% and 60%, respectively. Their intervals overlap. We describe these observed rates as similar without claiming that the models perform equally. Laya and GLiClass win 2% and 3% with the map alone, close to random. Full context raises their rates to 12% and 13%, but completion remains low.
// src: analysis/out/main.md

#figure(image("../../analysis/out/fig_main.pdf", width: 85%), placement: top,
  caption: [Compass won rate and progress with the map alone (pale) and full context (darker). Intervals resample puzzles. Each model/input uses 100 games.]) <fig:main>
// src: analysis/out/main.md; analysis/out/coverage.md

== Effects of input components

We compare the same puzzles with and without each component. For Jev, adding simulated outcomes to the map raises won rate by 16 percentage points [9, 23] and progress by {interval(sim, 'Progress change')}. Adding interaction history raises progress by {interval(history, 'Progress change')}. Both additions pass the Holm-adjusted won-rate test. These comparisons measure improvements over the map alone; they do not establish that simulations outperform history.
// src: analysis/out/components.md

The effect depends on what else the request contains. Including history in full context adds {interval(history_full, 'Progress change')} progress, whereas including simulated outcomes changes progress by {interval(sim_full, 'Progress change')}. Neither corresponding won-rate contrast passes Holm correction. Our interpretation is that several descriptions may help with the same decision, so a component's benefit alone need not mean it is needed with the others present.
// src: analysis/out/components.md

#figure(image("../../analysis/out/fig_components.pdf", width: 100%), placement: top,
  caption: [Paired change in won rate when a component is included. Circles compare adding it to the map alone; squares compare full context with and without it. Positive means inclusion helps. Filled markers identify McNemar tests that pass Holm correction.]) <fig:ablation>
// src: analysis/out/components.md

== Action spaces

For Jev with the map alone, won rate is 32% with compass moves, 40% with two-step sequences and 47% with three-step sequences. It falls to 26% when sequences of up to three steps are offered. With full context, the corresponding compass and up-to-three-step rates are 57% and 49%. Gemma's full-context rate is 61% under both formulations. Longer sequences therefore do not consistently improve completion. Each formulation also changes the number of options and the amount of text, so these results cannot be attributed to option count alone.
// src: analysis/out/action_spaces.md

#figure(image("../../analysis/out/fig_action_spaces.pdf", width: 100%), placement: top,
  caption: [Won rate with the map alone and full context across compass, two-step, up-to-two-step, three-step and up-to-three-step moves. Their option counts are 4, 16, 20, 64 and 84. More steps are executed before the next observation as well as more options being offered.]) <fig:rules>
// src: analysis/out/action_spaces.md

== Fixed-state evaluation

The planned shared-position experiment will ask every model the same compass questions with the map alone and with full context. It will complement complete games, where different models may encounter very different positions. #todo[fixed-state evaluation results]

== Blocked moves and progress

With the map alone, {percent(jev_map['Blocked moves'])} of Jev's moves leave the board unchanged. With full context, that share is {100 * float(jev['Blocked moves']):.1f}%. This reduction accompanies better completion, but does not by itself establish better route planning. Final-state progress is {float(jev['Final-state progress']):.3f}, below its closest-state progress of {float(jev['Progress']):.2f}. The distinction matters more for Qwen: its full-context scores are 0.560 and 0.66. A game can approach the goal and then finish farther away.
// src: analysis/out/main.md

== Completion by level

At levels {', '.join(r['Level'] for r in levels)}, Jev's full-context won rates are {', '.join(percent(r['Won rate']) for r in levels)}. Each level contains ten puzzles. Capped reasoning wins 70%, 40% and 30% at those levels with full context, compared with 50%, 20% and 20% with the map alone. The higher levels remain difficult even with reasoning. These rates describe the generated levels, which vary in layout as well as shortest-route length; they do not isolate the effect of distance.
// src: analysis/out/levels.md

#figure(image("../../analysis/out/fig_levels.pdf", width: 100%), placement: top,
  caption: [Compass won rate by level with the map alone and full context. Level is shortest-route distance in compass steps. Levels 1 and 2 have five puzzles each; every other level has ten.]) <fig:levels>
// src: analysis/out/levels.md

== Probability analysis

We pool all compass conditions and ask whether the chosen move was optimal. Jev assigns its chosen move a mean probability of {float(jc['Mean p(chosen)']):.3f}, while {percent(jc['Optimal share'])} of those moves are optimal. Its ECE is {float(jc['ECE']):.3f} and binary Brier score {float(jc['Brier']):.3f} over {int(jc['Moves']):,} moves. Laya's ECE is {float(lc['ECE']):.3f} with {100 * float(lc['Optimal share']):.1f}% optimality; Qwen's is {float(qc['ECE']):.3f} with {100 * float(qc['Optimal share']):.1f}% optimality. Low calibration error alone does not establish effective navigation. The models also reach different positions, so these scores are not comparisons on a shared set of questions.
// src: analysis/out/calibration.md

TypeSafe defines Choice confidence as $c = (p_(max) - 1/n) / (1 - 1/n)$ @typesafeconfidence. On all 14,642 Jev compass moves, the reported confidence differs from $(p_(max) - 1/n) / (1 - 1/n)$ by at most 0.023. For a fixed number of options, the formula ranks moves exactly as the top probability does. Reported confidence is therefore a rescaled score rather than an independent prediction of correctness.
// src: analysis/out/calibration.md (move count); TypeSafe confidence documentation; recorded confidence-formula check

#figure(image("../../analysis/out/fig_calibration.pdf", width: 60%), placement: top,
  caption: [Reliability after pooling all compass conditions. Each point compares mean chosen-move probability with the fraction of those moves that are optimal, accepting any tied best move. The diagonal indicates agreement between probability and observed optimality.]) <fig:reliability>
// src: analysis/out/calibration.md

== Cost and latency

The tables pool all compass conditions. Median inference time is {float(cost['Jev']['Median seconds per move']):.3f} seconds for Jev, {float(cost['Gemma 4 26B']['Median seconds per move']):.3f} for Gemma, and {float(cost['DeepSeek V4.1 Flash']['Median seconds per move']):.3f} for DeepSeek without reasoning. Capped reasoning takes {float(cost['DeepSeek V4.1 Flash (reasoning)']['Median seconds per move']):.3f} seconds. Recorded cost per 100 games is \\${float(cost['Gemma 4 26B']['Cost per 100 games ($)']):.3f}, \\${float(cost['DeepSeek V4.1 Flash']['Cost per 100 games ($)']):.3f} and \\${float(cost['DeepSeek V4.1 Flash (reasoning)']['Cost per 100 games ($)']):.3f}, respectively. Dollar costs are unavailable for Jev and the local models. These timings compare the evaluated services and hardware, not controlled implementations on the same machine.
// src: analysis/out/cost.md
''')

    write("conclusion", '''= Conclusion

Capped reasoning gives DeepSeek V4.1 Flash the highest observed completion rate among the models. Jev's full-context rate is similar to Gemma and DeepSeek without reasoning within overlapping intervals. Laya and GLiClass remain near random with the map alone. Supplying map-derived descriptions improves Jev's navigation, while offering longer sequences has mixed effects. Returned probabilities provide useful ranking information but are not uniformly calibrated to move optimality. The shared-position evaluation will test these decisions on common questions rather than the different positions reached during games.
// src: analysis/out/main.md; analysis/out/components.md; analysis/out/action_spaces.md; analysis/out/calibration.md; analysis/out/hypotheses.md; analysis/out/coverage.md
''')

    hypotheses = read("hypotheses")
    lines = ['// src: analysis/out/hypotheses.md; generated verbatim from matching CSV',
             '#figure(table(columns: (1fr, 1.5fr, auto), stroke: none, inset: 3pt,',
             'table.header([Hypothesis], [Observed result], [Criterion met]),']
    for row in hypotheses:
        lines.append(', '.join('text(' + json.dumps(row[k]) + ')' for k in ("Hypothesis", "Observed", "Criterion met")) + ',')
    lines.append('), caption: [Hypotheses specified before the main evaluation. Statements, observations and verdicts are copied from the analysis table.]) <tab:hyp>')
    (OUT / "hypothesis_table.typ").write_text('\n'.join(lines) + '\n', encoding="utf-8")
    lines = ['// src: analysis/out/components.md; all models and contrasts from matching CSV',
             '#figure([', '#set text(size: 8.5pt)', '#set par(leading: 0.25em)',
             '#table(columns: (1.2fr, 1fr, 1fr, 0.55fr, 1fr, 1fr, 0.55fr), stroke: none, inset: 2pt,',
             'table.header([Component], [Add: won change], [Add: progress], [Add: Holm p], [Full: won change], [Full: progress], [Full: Holm p]),']
    models = list(dict.fromkeys(r['Model'] for r in read('components')))
    for model in models:
        lines.append('table.cell(colspan: 7, text(weight: "bold", ' + json.dumps(model) + ')),')
        for component in ('local state description', 'interaction history', 'simulated action outcomes', 'explicit subgoal'):
            cells = [component]
            for direction in ('added to map only', 'removed from full context'):
                row = components[(model, component, direction)]
                cells.extend([interval(row, 'Won rate change'), interval(row, 'Progress change'), f"{float(row['Holm p']):.3f}"])
            lines.append(', '.join('text(' + json.dumps(cell) + ')' for cell in cells) + ',')
    lines.append(')], caption: [Complete paired component effects. Brackets give 95% intervals. Add and Full both report the effect of including the component.]) <tab:components>')
    (OUT / 'component_table.typ').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print("Synchronized results from current tables; reasoning games:", reason_map["Games"], reason["Games"])


if __name__ == "__main__":
    sync_results()
