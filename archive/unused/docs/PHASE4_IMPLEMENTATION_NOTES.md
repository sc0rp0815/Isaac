# Phase 4 – Umsetzung

Neu in Phase 4:
- Confirmation Policy / Security Analyzer mit persistenter Review-Queue
- Mid-Run-Resume für AI-Evaluations- und Search-Synthese-Checkpoints
- Replay-/Regression-Evals
- Memory-Block-History, Diff und Development-Timeline-API
- Security-Review-API

## Wichtige Grenzen
- Code/File-Side-Effect-Checkpoints werden beim Resume bewusst geblockt und verlangen Owner-Review.
- Mid-Run-Resume ist für AI- und Search-Tasks am stärksten; bei anderen Task-Typen bleibt Fallback auf Requeue/Restart.
