"""Authorization ("may it?") via OPA. See av/policy/opa.py and policies/authz.rego."""

from av.policy.opa import OpaPolicyEngine

__all__ = ["OpaPolicyEngine"]
