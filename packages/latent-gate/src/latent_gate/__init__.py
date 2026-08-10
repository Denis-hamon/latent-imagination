"""latent_gate — modèle-consequence servi en MCP/HTTP.

Recette mesurée (campagne Act II, pool v6 n=145, LOAO strict) :
  energy = 1 − cos(norm(E_state + E_diff), norm(E_state + E_goal))   [GOLD]
  f1     = d_nn(fail).min − d_nn(pass).min sur composites du pool     [goal-free]
  p      = σ(w ⋅ z(−energy, f1) + b)   logreg λ=1, fit all-pool (prod)
Verdict = p, avec abstention par quantiles de confiance out-of-fold.
"""

__version__ = "0.1.0"
