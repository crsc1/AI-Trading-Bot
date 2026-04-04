# Contributing

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your API keys
3. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Run tests: `pytest tests/ -v`

## Development

- **Lint**: `ruff check .`
- **Format**: `ruff format .`
- **Test**: `pytest tests/ -v`

## Security

- **Never** commit `.env` or files containing API keys
- Use `.env.example` as the template (no real values)
- The CI pipeline includes a secret scan that will fail if keys are detected

## Commit messages

Use clear, descriptive messages: `fix: resolve sidebar overflow in dashboard`, `feat: add ORB signal detection`.
