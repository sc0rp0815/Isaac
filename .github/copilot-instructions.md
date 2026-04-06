# Isaac – Repository Instructions for Copilot

Isaac is not a generic chatbot project.
Isaac is a personal, local, trust-based, privacy-first, development-oriented AI core.

## Core principles

- Prefer local-first and privacy-preserving designs.
- Never assume raw user input should be sent externally without decomposition, abstraction, or minimization.
- Favor causal clarity over quick hacks.
- Favor meaningful coupling between modules over isolated feature growth.
- Treat trust, meaning, memory, values, and state as first-class architectural concerns.
- Isaac should evolve toward a coherent personal system, not a pile of disconnected utilities.

## What Isaac is not

- Not a generic SaaS chatbot
- Not a girlfriend bot
- Not a shallow assistant with fake emotional simulation
- Not a cloud-first prompt relay
- Not a feature pile without architectural consistency

## Coding guidance

- Before adding a feature, identify which of these it affects:
  - memory
  - trust / privilege
  - meaning / values
  - state / background behavior
  - privacy / decomposition
  - causal coupling between modules
- Prefer explicit, readable logic over hidden side effects.
- Document non-obvious coupling decisions.
- Avoid introducing functionality that breaks local control or privacy posture.
- Avoid “quick fixes” that contradict long-term architecture.

## Architectural direction

Isaac should move:
- from modular adjacency
- toward causally explainable internal coupling

Important dependency classes:
- technical dependencies
- causal dependencies
- decision dependencies
- state dependencies
- temporal dependencies
- memory dependencies
- values / meaning dependencies
- educational dependencies

## Interaction philosophy

- Relationship should emerge from memory, repeated interaction, trust, context, and shared history.
- Do not simulate emotional closeness just because it seems engaging.
- Prefer meaningful, rare, contextually justified interventions over noisy interaction.

## Device / future-facing mindset

Future Isaac-related work may involve:
- physical embodiment
- situational behavior design
- sensor / environment integration
- device-to-device interaction
- adaptive personality expression without mass-produced sameness

## Change policy

When suggesting edits:
1. explain the architectural reason
2. keep changes scoped
3. preserve future extensibility
4. do not flatten Isaac into a generic assistant architecture
