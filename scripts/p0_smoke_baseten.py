"""P0 smoke test: one tiny live call to Spark Open on Baseten. Never prints the key."""
import os, sys, time, httpx

key = os.getenv("BASETEN_API_KEY")
if not key:
    sys.exit("BASETEN_API_KEY not set; refusing to run (no dry run for P0).")
model = "meta-models/muse-spark-open-1026"
t = time.time()
r = httpx.post("https://inference.baseten.co/v1/chat/completions",
               headers={"Authorization": f"Bearer {key}"},
               json={"model": model, "max_tokens": 512,
                     "messages": [{"role": "user", "content": "Reply with the single word: ready"}]},
               timeout=90)
r.raise_for_status()
d = r.json()
u = d.get("usage", {})
print(f"model={model} id={d.get('id')} latency_s={time.time()-t:.2f} "
      f"in={u.get('prompt_tokens')} out={u.get('completion_tokens')} "
      f"text={d['choices'][0]['message'].get('content')!r}")
