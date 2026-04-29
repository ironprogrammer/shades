# Contributing

Thanks for your interest in contributing to shades!

## Before you start

Open an issue first to discuss any significant change — it avoids duplicated effort and makes sure the direction fits the project before you invest time in a PR.

For small fixes (typos, broken links, minor bugs), a PR is fine without an issue.

## Pull requests

- Keep changes focused. One feature or fix per PR.
- Update the README if your change affects setup, CLI usage, or scene authoring.
- Make sure tests pass: `python3 -m pytest tests/ -v`
- Add tests for new behavior where it makes sense.

## Code style

- Follow the existing style in whatever file you're editing.
- No inline comments explaining *what* code does — good names do that. Comments are for *why* something non-obvious is done.
- Keep it simple. Don't add abstractions or error handling for cases that can't happen.

## Issues

Bug reports are welcome. Please include:

- What you expected to happen
- What actually happened
- Relevant output or error messages
- Your OS, Python version, and hub model if applicable
