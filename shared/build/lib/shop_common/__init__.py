"""Shared helpers used by every service and the gateway.

Only cross-cutting plumbing lives here (telemetry, logging, metrics). Business logic never does:
each bounded context keeps its own models and rules inside its own service.
"""
