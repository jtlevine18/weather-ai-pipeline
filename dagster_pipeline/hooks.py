"""
Hooks — success / failure callbacks that emit structured JSON events
so external systems (or the event bus) can react to pipeline outcomes.
"""

from dagster import success_hook, failure_hook, HookContext

from src.event_bus import EventBus


@success_hook
def pipeline_success_hook(context: HookContext):
    """Publish a success event via the event bus."""
    bus = EventBus()
    bus.publish("pipeline.completed", {
        "status": "success",
        "run_id": context.run_id,
    })
    context.log.info(f"Pipeline succeeded (run {context.run_id}).")


@failure_hook
def pipeline_failure_hook(context: HookContext):
    """Publish a failure event via the event bus."""
    bus = EventBus()
    bus.publish("pipeline.failed", {
        "status": "failure",
        "run_id": context.run_id,
        "error": str(context.op_exception) if context.op_exception else "unknown",
    })
    context.log.info(f"Pipeline failed (run {context.run_id}).")
