import os
import pathlib

import kaggle_benchmarks as kbench
import requests
from kaggle_benchmarks import envs
from kaggle_benchmarks.kaggle import models

from benchmark.envs import LocalEnvironment
from benchmark.infrastructure import get_log_filename, VirtualFileSystem, get_run_logger
from benchmark.persistent_folder import PersistentFolder
from benchmark.telemetry import enable_logging, set_log_file
from benchmark.tasks import run_adaptive_learning, adaptive_learning
from benchmark.legacy_tasks import terminal_chain, infrastructure_evolution

# By default, if kbench.llm points to Google Gemini, it's created as OpenAI-compatible model.
# Let's recreate it as a "genai" model.
if kbench.llm.name.startswith("google/gemini-"):
    llm = models.load_model(model_name=kbench.llm.name, api="genai")
else:
    llm = kbench.llm


# llm = models.load_model(model_name="google/gemini-3-flash-preview", api="genai")
# llm = models.load_model(model_name="anthropic/claude-opus-4-6@default", api="openai")
# llm = models.load_model(model_name="deepseek-ai/deepseek-v3.2", api="openai")
llm = models.load_model(model_name="openai/gpt-5.4-mini-2026-03-17", api="openai")

# Then, let's enable logging and set up a working directory

enable_logging()
log_filename = get_log_filename("kaggle", llm.name)
set_log_file(f"/kaggle/working/{log_filename}")
# Create a new local environment and point our VirtualFileSystem to the temporary folder
envs.current = LocalEnvironment()
VirtualFileSystem.override_root(envs.current.directory)
os.symlink(envs.current.directory, f"/kaggle/working/{log_filename}-working-dir", target_is_directory=True)


def upload_file(filename: str | pathlib.Path) -> str:
    """
    Upload a file from Kaggle to https://tmpfiles.org and return the URL.
    It's useful to share the logs and working directory because Kaggle removes everything after 40 minutes of inactivity
    """
    with pathlib.Path(filename).open("rb") as f:
        response = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": f},
            data={
                # optional:
                # "expires": "1d",      # examples: 1d, 1w, 1m, 1y
                # "maxDownloads": 1,
                # "autoDelete": "true",
            },
            timeout=30,
        )

    response.raise_for_status()
    result = response.json()
    return result["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


# Finalizer
def finalize():
    print("Download logs: ", upload_file(get_run_logger()._path))
    persistent_folder = PersistentFolder(envs.current.directory)
    checkpoint_path = persistent_folder.get_checkpoint_path(persistent_folder.save_checkpoint())
    print("Download working directory: ", upload_file(checkpoint_path))


# To run a task, uncomment one of the following calls. This will take a while:

try:
    # terminal_chain.run(llm, terminal_spec="dummy")
    # terminal_chain.run(llm, terminal_spec="sys32-maze")
    # terminal_chain.run(llm, terminal_spec="maze-sys32")
    # terminal_chain.run(llm, terminal_spec="maze-maze")
    # terminal_chain.run(llm, terminal_spec="sys32-maze-sys32")
    # terminal_chain.run(llm, terminal_spec="maze-sys32-maze")
    #
    # infrastructure_evolution.run(
    #    llm,
    #    training_terminals=["sys32(10)", "strings(10)", "hash(10)", "sys32(20)-strings(20)", "hash(20)-sys32(30)", "strings(30)-hash(30)"],
    #    validating_terminals=["sys32(10)", "strings(10)", "hash(10)", "sys32(20)-strings(20)", "hash(20)-sys32(30)", "strings(30)-hash(30)",
    #                          "sys32(100)", "strings(100)", "hash(100)", "sys32(200)-strings(200)", "hash(200)-sys32(300)", "strings(300)-hash(300)"],
    # )
    #
    # Adaptive Learning Task
    adaptive_learning.run(llm, generators=None)
    # run_adaptive_learning(llm)
    ...
finally:
    finalize()
