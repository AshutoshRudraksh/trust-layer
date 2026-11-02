Reflexion reaches 91.0 Pass@1 on HumanEval (PY) versus 80.1 for GPT-4, a gain of 11.9 points (Table 1).

On Leetcode Hard (PY), Pass@1 rises from 7.5 to 15.0, which doubles it (Table 1).

In the ablation (Table 3), omitting test generation drops Pass@1 from 0.60 to 0.50, while full Reflexion reaches 0.68.

The largest HotPotQA gain is ReAct + text-davinci-003, from 0.30 to 0.55, a gain of 0.25 (Table 5).

MBPP (PY) is the only row where Reflexion (0.77) is below the base (0.80) (Table 2).

The architecture (Figure 2) has two models: the Actor and the Self-reflection model.

The trajectory serves as short-term memory and the reflections are stored in long-term memory.

The MBPP regression happens because the benchmark is too easy.
