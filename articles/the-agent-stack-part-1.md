# The Agent Stack - Part 1: A Systems Map of Modern Agent Infrastructure

**Author:** Vinoth Govindarajan  
**Date:** March 30, 2026  
**Source:** https://theagentstack.substack.com/p/the-agent-stack-part-1-a-systems

## Overview

This article argues that "agent" has become an overloaded term obscuring more than it explains. Rather than a single entity, Govindarajan proposes viewing agent infrastructure as a **stack of distinct layers**, each with different ownership and accountability.

## Key Problem

The term "agent" now gets applied to provider APIs, workflow runtimes, browser operators, and memory systems indiscriminately. As Govindarajan notes: *"Once the same label covers state ownership, orchestration, capability exposure, and execution"* the term loses diagnostic value.

## The 10-Layer Stack

1. Interfaces and channels
2. Control plane and session ownership
3. Runtime, workflows, and durable execution
4. Model engine and inference
5. Context, retrieval, and memory
6. Tools, MCP, and capability surfaces
7. Execution surfaces
8. Identity, trust, policy, and approvals
9. Observability, evaluation, and feedback loops
10. Infrastructure substrate

## Critical Distinctions

The author emphasizes separating commonly confused concepts:

- **Session ≠ Authorization**: Sessions identify which interaction owns a turn; authorization determines permissions
- **Tools ≠ Execution**: Tool schemas show what requests are possible; execution surfaces determine actual effects
- **Approval ≠ Isolation**: Approval gates decide whether actions proceed; sandboxes limit what those actions can do

## Why This Matters

Collapsing these boundaries creates architecture errors with real consequences: unnecessary costs, degraded performance, misdiagnosed incidents, and lost audit trails.

The stack model provides a better analytical framework for building and debugging agent systems than treating them as monolithic entities.
