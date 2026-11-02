Agentless with GPT-4o resolves 96 of 300 SWE-bench Lite problems, 32.00% (Table 1).

Average cost is $0.07 per issue with 78,166 average tokens (Table 1).

Patch selection (Table 4): majority voting gives 77, adding regression tests gives 81, and adding reproduction tests gives 95, so reproduction tests add 14.

Repair (Table 3): multi-samples (4 x 10 samples) resolve 96 versus 88 for greedy location (40 samples), 8 more.

File level localization (Table 2): combined reaches 81.67% versus 78.67% for prompting, 3.00 points higher.

Agentless has three phases (Figure 1): localization, repair, and selection.

On SWE-bench Verified it resolves 194 issues, 38.80% (Table 6).

The skeleton format wins because it was written later.
