import kaggle_benchmarks as kbench
import requests
from kaggle_benchmarks import envs

from benchmark.infrastructure import run_agent_loop, _get_status
from benchmark.tasks import TERMINAL_BUILDER, TaskEnvironment
from benchmark.telemetry import emit_event


@kbench.task(name="terminal_chain")
def terminal_chain(
    llm,
    terminal_spec: str = "sys32",
    seed: int = 42,
    max_steps: int = 100,
) -> bool:
    """
    Run the benchmark against an explicit terminal chain spec.

    The chain spec is outermost-first and always ends in an implicit `main`
    terminal unless the entire spec is exactly `main`.
    """
    outer_terminal = TERMINAL_BUILDER.build(terminal_spec, default_seed=seed)

    outer_welcome_message = outer_terminal.get_welcome_message()
    with TaskEnvironment(outer_terminal) as env:
        run_agent_loop(
            llm,
            env.server_url,
            env.server_url_for_model,
            env.vfs,
            outer_welcome_message=outer_welcome_message,
            max_steps=max_steps,
            terminal_spec=terminal_spec,
            seed=seed,
        )

    return True


@kbench.task(name="infrastructure_evolution")
def infrastructure_evolution(llm, training_terminals: list[str] | None = None, validating_terminals: list[str] | None = None) -> tuple[int, int]:
    if training_terminals is None:
        training_terminals = [
            "sys32(10)",
            "sys32(20)",
            "sys32(10)",
            "sys32(20)",
        ]
    if validating_terminals is None:
        validating_terminals = [
            "sys32(20)",
            "sys32(10)",
        ]

    with TaskEnvironment() as env:
        for outer_loop_index, terminal_spec in enumerate(training_terminals):
            terminal = TERMINAL_BUILDER.build(terminal_spec)
            env.replace_outer_terminal_on_server_and_reset(terminal)

            run_agent_loop(
                llm,
                env.server_url,
                env.server_url_for_model,
                env.vfs,
                outer_welcome_message=terminal.get_welcome_message(),
                max_steps=100,
                terminal_spec=terminal_spec,
            )

            checkpoint_id = env.persistent_folder.save_checkpoint()

            number_of_passed_validating_terminals = 0
            for validating_terminal_spec in validating_terminals:
                env.persistent_folder.restore(checkpoint_id)

                emit_event(event_type="validation", actor="benchmark", iteration=None, terminal_spec=validating_terminal_spec)

                terminal = TERMINAL_BUILDER.build(validating_terminal_spec)
                env.replace_outer_terminal_on_server_and_reset(terminal)

                try:
                    run_result = envs.current.run("python main.py", input=None)
                except Exception as e:
                    run_result = envs.RunResult(exit_code=-1, stdout="", stderr=str(e))

                status = _get_status(env.server_url)
                emit_event(event_type="validation_result", actor="benchmark",
                           iteration=None,
                           terminal_spec=validating_terminal_spec,
                           exit_code=run_result.exit_code,
                           stdout=run_result.stdout,
                           stderr=run_result.stderr,
                           status=status)

                is_validating_terminal_passed = status.get("done", False)
                if is_validating_terminal_passed:
                    number_of_passed_validating_terminals += 1

            emit_event(event_type="validation_summary", actor="benchmark",
                       iteration=None,
                       number_of_passed_validating_terminals=number_of_passed_validating_terminals,
                       total=len(validating_terminals))

            if number_of_passed_validating_terminals == len(validating_terminals):
                # Earlier → better → larger score
                return len(training_terminals) - outer_loop_index, len(training_terminals)

            env.persistent_folder.restore(checkpoint_id)

    return 0, len(training_terminals)

