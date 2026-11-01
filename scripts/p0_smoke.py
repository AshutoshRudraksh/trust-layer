"""P0 smoke test: one tiny live call on the Contributor tier. Never prints the key."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.meta_client import MetaModelClient

if not os.getenv("MODEL_API_KEY"):
    sys.exit("MODEL_API_KEY not set; refusing to run (no dry run for P0).")
c = MetaModelClient(budget_cap_usd=40.0)
t = time.time()
r = c.respond("Reply with the single word: ready", role="eval-runner",
              model="muse-spark-1.3-contributor", reasoning_effort="low",
              max_output_tokens=512, endpoint_style="chat_completions")
print(f"model={r.model} id={r.response_id} latency_s={time.time()-t:.2f} "
      f"in={r.input_tokens} out={r.output_tokens} est_cost_usd={r.cost_usd} text={r.output_text!r}")
