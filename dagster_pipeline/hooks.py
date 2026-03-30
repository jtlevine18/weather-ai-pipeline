"""
Hooks — success / failure callbacks for pipeline outcomes.
"""

from dagster import success_hook, failure_hook, HookContext


@success_hook
def pipeline_success_hook(context: HookContext):
    context.log.info(f"Pipeline succeeded (run {context.run_id}).")


@failure_hook
def pipeline_failure_hook(context: HookContext):
    context.log.error(f"Pipeline failed (run {context.run_id}): {context.op_exception}")
