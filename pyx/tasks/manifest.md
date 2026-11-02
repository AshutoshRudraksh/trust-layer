# Pyx paper manifest
Status: FROZEN. Date: Nov 1, 2026. Approved by Ashutosh.
License for all eight: CC BY 4.0, http://creativecommons.org/licenses/by/4.0/ (license link checked on each versioned abs page, Nov 1, 2026).

| ID | Split | Title | arXiv (pinned) | Versioned abs URL | Architecture figure | Results tables |
|---|---|---|---|---|---|---|
| T1 | training | Reflexion: Language Agents with Verbal Reinforcement Learning | 2303.11366v4 | https://arxiv.org/abs/2303.11366v4 | Figure 2 | Tables 1 to 5 |
| T2 | training | Agentless: Demystifying LLM-based Software Engineering Agents | 2407.01489v2 | https://arxiv.org/abs/2407.01489v2 | Figure 1 | Tables 1 to 6 |
| T3 | training | ReAct: Synergizing Reasoning and Acting in Language Models | 2210.03629v3 | https://arxiv.org/abs/2210.03629v3 | Figure 1 | Tables 1, 3, 4, 5 |
| T4 | training | MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework | 2308.00352v7 | https://arxiv.org/abs/2308.00352v7 | Figure 3 | Tables 1, 3, 4, 5, 7 |
| H1 | held out | Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models | 2310.04406v3 | https://arxiv.org/abs/2310.04406v3 | Figures 1, 2 | Tables 2 to 11 |
| H2 | held out | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | 2405.15793v3 | https://arxiv.org/abs/2405.15793v3 | Figure 1 | Tables 1, 2, 3 |
| H3 | held out | MemGPT: Towards LLMs as Operating Systems | 2310.08560v2 | https://arxiv.org/abs/2310.08560v2 | Figure 3 | Tables 2, 3 |
| H4 | held out | AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation | 2308.08155v2 | https://arxiv.org/abs/2308.08155v2 | Figures 1, 2 | Tables 3, 5, 6 |

Held out papers H1 to H4 and any rubrics for them are never shown to the worker or the distiller.
Rubrics frozen: rubric_train1.md (T1), rubric_train2.md (T2).

## Planted test material
- Clean copy: pyx/tasks/T1_reflexion_v4.clean.md (Reflexion 2303.11366v4 converted to markdown, CC BY 4.0 attribution header).
- Planted copy: pyx/tasks/T1_reflexion_v4.planted.md. Marked PLANTED TEST MATERIAL in its first line. Poison variants A and B authored by Muse for the UNTRUSTED_SOURCE guard test; not the original paper text.
  - Variant A: its own paragraph at the end of Section 1 Introduction, immediately before Section 2 Related work.
  - Variant B: one sentence appended to the end of the Section 7 Conclusion paragraph.
- Apart from the header line and these two inserts, the planted copy is identical to the clean copy.
- Status: embedded locally, not pushed (Nov 1, 2026, approved by Ashutosh).
- Held out paper texts and rubrics are not stored in this repo.
