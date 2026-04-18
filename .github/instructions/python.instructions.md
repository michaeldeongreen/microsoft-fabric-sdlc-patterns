---
applyTo: "**/*.py"
---

When generating or improving Python code in this repository:

## Style & Structure
- Target Python 3.10+ (use `X | Y` union syntax, not `Union[X, Y]`)
- Use `pathlib.Path` over `os.path` for all file operations
- Use type hints on function signatures
- Use f-strings for string formatting, never `.format()` or `%`
- Use `subprocess.run()` with `check=True` instead of `os.system()` or `subprocess.call()`
- Prefer `sys.exit("message")` over `raise SystemExit`
- Constants at module level in `UPPER_SNAKE_CASE`

## Error Handling
- Catch specific exceptions, never bare `except:`
- Use `sys.exit(1)` for fatal script errors with a clear message to stderr
- Validate external inputs (user input, file contents, API responses) at boundaries

## File I/O
- Always specify `encoding="utf-8"` when opening text files
- Use `json.loads(path.read_text())` for small JSON files
- Use context managers (`with` statements) for file handles when streaming

## Dependencies
- Keep scripts stdlib-only when possible; gate optional imports with try/except
- When external packages are needed, prefer: `requests`, `azure-identity`
- Never pin to exact versions in scripts; use `>=` minimum bounds in requirements files

## Security
- Never hardcode secrets, tokens, or credentials
- Strip notebook META blocks containing internal metadata before committing
- Validate GUIDs and IDs from external sources before using them in paths or URLs
- Use `secrets` module for generating random tokens, not `random`

## Testing & Validation
- Scripts should exit non-zero on failure
- Print a summary of actions taken before exiting
- Use `--dry-run` flags for destructive operations when practical
