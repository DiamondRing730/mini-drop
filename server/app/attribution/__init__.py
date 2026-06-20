"""AI smart attribution: a constrained tool-calling analyst over a profile.

The LLM (or the deterministic fallback) may only inspect the profile through the
read-only tools in `tools.py`; the verifier in `verifier.py` independently re-checks
every numeric claim against the raw profile so a hallucinated number cannot pass.
"""
