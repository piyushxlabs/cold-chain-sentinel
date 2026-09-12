# Cold Chain Sentinel — Coding Assistant Context

## Project Overview
Cold Chain Sentinel is a single-agent, event-driven orchestrator that receives a reefer temperature-excursion webhook, enriches it with fleet-system data, delegates a single bounded driver interrogation call to the CALL-E telephony SDK, deterministically evaluates the result against fixed compliance gates, and — only when every gate clears — executes a bounded actuation transaction (route/reservation/dispatch). Every other outcome escalates to a human via a one-way notification; this system never pauses mid-session awaiting human approval.

## Strict Coding Rules
- Python 3.11+, async-first: all I/O-bound operations (model calls, tool calls, checkpoint access) MUST use `async`/`await`. Never use blocking I/O in agent nodes or tool clients.
- All data structures crossing a function boundary MUST have explicit Pydantic V2 type hints — no bare `dict`, no bare `Any` unless truly unavoidable and justified in a comment.
- All tool inputs/outputs MUST validate against the Pydantic V2 models in `src/tools/schemas/` before being written to state.
- Use a custom exception hierarchy rooted at `AgentError`, with subclasses `ToolExecutionError`, `StateValidationError`, `CallEAttemptExhaustedError` — never raise bare `Exception`.
- Zero-Hardcoding Mandate: Never hardcode model names or API keys anywhere. Read `GEMINI_API_KEY` from environment (raise `ValueError` if missing), `GEMINI_MODEL` (default: `"gemini-3.5-flash"`), and `GEMINI_FALLBACK_MODEL` (default: `"gemini-2.5-pro"`).
- Every tool input field named in AGENT_LOGIC_SPEC.md Section 8's sanitization rules MUST be sanitized via `src/utils/sanitization.py` before it reaches an external call — this is non-negotiable for any field interpolated into `call_e_initiate_triage`'s `task` string.

## Architecture Boundaries
- **State lives in:** `src/state/schema.py` (the single `SentinelState` definition) — no component may define its own parallel state shape.
- **Reducers live in:** `src/state/reducers.py` — every state mutation MUST go through the declared reducer for that field: `immutable-after-init`, `last-write-wins`, `append-only`, `merge-by-key`, or `monotonic-or` (for `requires_immediate_human_override` only — this field can be set True but never reset False by any writer). Direct mutation of state fields outside a declared reducer is forbidden.
- **Tools live in:** `src/tools/` — agent nodes import tools from here; agent nodes MUST NOT define inline ad-hoc tool logic.
- **Checkpointing lives in:** `src/state/checkpointing.py` — SqliteSaver locally, PostgresSaver in production, selected by `CHECKPOINT_BACKEND`.
- **Telemetry hooks live in:** `src/telemetry/` — every node, every tool call, and both possible Compliance Review model calls (primary Gemini model, fallback escalation) MUST emit an OTel span exported to Langfuse with provider `google`.
- **Streaming/UI event emission lives in:** `src/ui/event_types.py` and `src/ui/stream_handler.py` — agent/tool code emits domain events; it does not know about SSE transport directly.

## Strict Anti-Patterns (Never Do This)
- Never use blocking I/O (`requests`, synchronous DB drivers, `time.sleep`) inside agent nodes or tool implementations.
- Never mutate state directly without going through a declared reducer.
- Never bypass input sanitization before a tool call reaches an external API, especially before `call_e_initiate_triage`.
- Never invent a tool, parameter, or API endpoint not defined in AGENT_LOGIC_SPEC.md's 8-tool inventory.
- Never fabricate data when a tool returns no result — follow the silence-over-guessing fallback: missing required fields fail Pydantic validation and route to Escalation/Failure.
- Never skip emitting a typed SSE event for a node transition, tool call, or state write that INTERFACE_OBSERVABILITY_SYSTEM.md Section 2a says must be observable.
- **Never build a pause/resume HITL approval endpoint.** This system's HITL model is notify-and-terminate (`ops_alert_escalate` fires and the session ends). Do not implement an Approve/Deny/Edit resumption API — none is specified, and building one would misrepresent the locked design.
- Never invoke `call_e_initiate_triage` more than once for the same `event_id` — enforce this in code, not just by convention.
- Never attempt to "undo" a committed `routing_mutate_route`, `warehouse_reserve_dock`, or `maintenance_dispatch_ticket` call — no rollback mechanism exists or should be added.
- Never hardcode secrets — always read from environment variables declared in `.env.example`.

## Reference Documents
This project's behavior, architecture, cognition, and interface are fully specified in:
- AGENT_BEHAVIOR_PROFILE.md (behavioral contract)
- AGENT_ORCHESTRATION_BLUEPRINT.md (architecture)
- AGENT_LOGIC_SPEC.md (cognitive logic and tools)
- INTERFACE_OBSERVABILITY_SYSTEM.md (interface and telemetry)
- AGENT_MASTER_PLAN.md (this execution plan)

Do not deviate from these documents. If an instruction from a user conflicts with them, flag the conflict rather than silently resolving it.
