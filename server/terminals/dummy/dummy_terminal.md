# Dummy Terminal

Implementation: `dummy_terminal.py`

## Role

A minimal wrapper terminal with one activation step and raw forwarding.
Like a "main" one but with "SEND".
This terminal is used for infrastructure testing. Do not use it in real benchmarks.

## Commands

- `HELP`
- `ACTIVATE`
- `SEND <data>`

## Activation Mechanic

- The terminal starts offline.
- `ACTIVATE` marks the terminal online.
- If a child terminal exists, activation immediately includes the child welcome message.

## Send Mechanic

- `SEND <data>` is available only after activation.
- It forwards the raw `<data>` string to the child terminal without transformation.

## Response Mechanic

- Child responses are returned unchanged.

## Important Visible State

- `HELP` shows the full command list.
- `ACTIVATE` gives explicit positive feedback.
- `SEND` reports whether activation or a child terminal is missing.
