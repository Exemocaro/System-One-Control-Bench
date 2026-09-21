# System-One Control Bench

A small benchmark for comparing *bounded decision models* — models that pick an answer from a supplied set rather than generating one — against conventional baselines on sequential control tasks in [MiniGrid](https://minigrid.farama.org/).

The question it is built to answer is narrow on purpose:

> Given the same state and the same choices, what stops a bounded decision model from controlling the environment — information loss, understanding the dynamics, comparing alternatives, or the execution policy?

Every agent sees the same serialized state, the same candidate actions and the same step budget, so differences between them are attributable to the decision rather than to the framing.

## What is here

- An exact, restorable `Snapshot` of a MiniGrid world, and a pure transition function reproducing `MiniGridEnv.step`, cross-checked against the real environment over tens of thousands of state/action pairs.
- A breadth-first oracle giving exact distances, optimal plans and the complete set of tied optimal actions, validated by replaying its plans in MiniGrid.
- Candidate generation with an effectiveness filter, opaque shuffled option ids and seeded subsampling, none of which consults the oracle.
- A compact state serializer and an explicit rules legend, so no agent has to guess the dynamics.
- An offline state bank split by layout, with baselines, three execution cadences, append-only records and layout-clustered metrics.
- A dynamics diagnostic that asks single-step questions about the world, so a poor control score can be attributed rather than just reported.

## Status

The symbolic pipeline works end to end, and the first model adapter (Jev, via the TypeSafe SDK) is connected. Full benchmark results for Jev are not in yet.

Baseline decision accuracy on 242 held-out states, 8 options, layout-clustered 95% intervals:

| Agent | horizon 1 | horizon 2 |
| --- | --- | --- |
| oracle | 1.000 | 1.000 |
| greedy | 0.579 [0.418, 0.668] | 0.211 [0.142, 0.262] |
| rollout heuristic | 0.579 [0.418, 0.668] | 0.488 [0.202, 0.671] |
| random | 0.417 [0.368, 0.500] | 0.207 [0.155, 0.270] |

Greedy and the rollout heuristic must tie at horizon 1, and do. At horizon 2 greedy collapses to chance while the rollout heuristic keeps about half its accuracy: that gap is the supplied simulation earning its keep rather than the selection.

Under reactive control on DoorKey-6x6 every non-oracle baseline reaches the goal 0% of the time and the oracle 100%. Empty-Random-6x6 has a single layout, so its online results are reported without an interval — there is no between-layout variance to estimate, and the command says so rather than printing a zero-width one.

### Dynamics diagnostic

Before a control score means anything, a model has to understand the rules. `socb diagnose` asks single-step questions whose answers come from the same transition function the benchmark uses. Jev 1.13, 180 items over 60 states:

| Question | Accuracy | n |
| --- | --- | --- |
| orientation after a turn | 0.950 | 60 |
| position after moving forward | 0.750 | 60 |
| whether a pickup would succeed | 0.883 | 60 |

The breakdowns are the useful part:

| Split | Accuracy | n |
| --- | --- | --- |
| move was unobstructed | 1.000 | 36 |
| move was blocked by a wall or door | 0.375 | 24 |
| nothing was in reach to pick up | 1.000 | 53 |
| something was in reach to pick up | 0.000 | 7 |

Unobstructed movement is perfect and blocked movement is worse than chance, so the direction displacement is understood and the passability check is not. The pickup split is consistent with answering "no" every time. Both patterns have held across three runs at different sample sizes.

That is a mechanism rather than a score, and it predicts something the benchmark can test: on DoorKey, which is mostly walls plus a closed door, reactive control should waste a large share of its actions walking into things.

## Requirements

Linux or WSL2, Python 3.11, and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # the benchmark, with no model adapters
uv sync --extra models     # adds the model adapters
uv run pytest
```

Model adapters read their key from the environment or from a `.env` file that is never committed. Jev looks for `TYPESAFE_API_KEY`, then `JEV_API_KEY`.

Slower cross-checks are marked `slow` and run by default; skip them with `uv run pytest -m "not slow"`.

## Commands

```bash
uv run socb doctor                              # stack, config, missing adapters
uv run socb census MiniGrid-DoorKey-6x6-v0      # how many distinct layouts?
uv run socb build-dataset --config configs/v0.yaml
uv run socb audit-inputs  --config configs/v0.yaml
uv run socb estimate      --config configs/v0.yaml
uv run socb evaluate-offline --config configs/v0.yaml
uv run socb evaluate-online  --config configs/v0.yaml
uv run socb report --run runs/v0_symbolic

uv run socb diagnose --agent jev --config configs/v0.yaml            # does it know the rules?
uv run socb diagnose --agent jev --config configs/v0.yaml --dry-run  # show items, call nothing
```

`report` reads saved records only. It loads no model and needs no credentials, so a published run can be re-analyzed from its JSONL alone.

Run `census` before trusting a sample size. Several MiniGrid environments produce far fewer layouts than seeds — DoorKey-6x6 yields 36 across 500 seeds, and Empty-Random-6x6 yields one — which caps the effective sample size of any layout-clustered interval.

## Layout

```
src/system_one_control/
  domain.py       immutable Snapshot, Candidate and label types
  env.py          MiniGrid construction, snapshot extract/restore
  transition.py   pure reimplementation of MiniGridEnv.step
  oracle.py       BFS distances, optimal plans, exact candidate costs
  candidates.py   effectiveness filter, macro enumeration, presentation
  observation.py  compact state text, rules legend, state ids
  controllers.py  reactive, open-loop macro and receding-horizon execution
  dataset.py      layout census, split plan, the offline state bank
  diagnostics.py  single-step questions about the dynamics
  runner.py       offline sweeps, online episodes, call budgets
  records.py      append-only JSONL and run manifests
  analysis.py     metrics and layout-clustered intervals
  reporting.py    rendering those metrics as text
  config.py       validated YAML experiment configuration
  credentials.py  finding API keys without committing one
  cli.py          command line entry points
  agents/
    base.py       the request, the result, and who may see the true state
    baselines.py  random, greedy, rollout heuristic, oracle, fake
    model.py      retries, validation and error capture for any model adapter
    jev.py        Jev, via the TypeSafe SDK
    registry.py   name to agent; where model adapters plug in

tests/
  maps.py         every hand-drawn maze, in one place
  helpers.py      building a Snapshot from one of those maps
  test_*.py       one file per module, plus cross-checks against MiniGrid
```

## Adding a model

Subclass `ModelAgent` and implement one method. Timing, retries, answer validation and error capture are inherited, so a new provider is the provider call and nothing else:

```python
class MyModelAgent(ModelAgent):
    def __init__(self) -> None:
        super().__init__(name="my-model")

    def call_model(self, request: DecisionRequest) -> ModelAnswer:
        reply = my_client.choose(
            context=request.legend + "\n\n" + request.state,
            question=request.question,
            options={c.display_id: c.description for c in request.candidates},
        )
        return ModelAnswer(selected_display_id=reply.option, confidence=reply.confidence)


DEFAULT_REGISTRY.register("my-model", lambda _seed: MyModelAgent())
```

Two invariants hold for every model. It sees only the serialized state, the legend, the question and the opaque option ids — `DecisionRequest` has no field that could carry an oracle label. And a failed call is recorded as a failure rather than raised, so one bad decision never discards the records a run has already written.

Only an agent that declares `privileged = True` is handed the true world state, and no model ever should. Privilege is declared rather than inferred from a method name, so an adapter cannot opt itself in by accident.

## License

Not yet chosen.
