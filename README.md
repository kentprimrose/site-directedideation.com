# site-directedideation.com

site-directedideation.com



## Requirements

- The exact Python version recorded in `.python-version`
- [uv](https://docs.astral.sh/uv/)
- Optional: [direnv](https://direnv.net/)


## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Apply automatic formatting and safe lint fixes:

```bash
uv run ruff format .
uv run ruff check --fix .
```


## CI

Install exactly the dependencies recorded in `uv.lock`:

```bash
uv sync --all-groups --frozen
```
