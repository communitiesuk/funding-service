# GitHub Copilot Instructions for Funding Service

## Project Overview

This is the Funding Service, a Flask-based Python web application for managing grant funding. The application follows UK Government Digital Service (GDS) patterns and uses the GOV.UK Design System.

## Technology Stack

- **Backend**: Python 3.13.7, Flask 3.1+, SQLAlchemy 2.0+
- **Frontend**: Vite, JavaScript (ES modules), Sass, GOV.UK Frontend 5.13
- **Database**: PostgreSQL with Alembic migrations
- **Testing**: pytest, playwright (E2E), vitest (frontend)
- **Linting**: Ruff (Python), Prettier (HTML/CSS/JS)
- **Package Management**: uv (Python), npm (JavaScript)

## Code Style and Conventions

### Python

- Follow PEP 8 and use Ruff for linting (config in `pyproject.toml`)
- Line length: 120 characters
- Use type hints (strict mypy enabled)
- Use Python 3.13 features
- Import order: isort style (handled by Ruff)
- Format with Ruff's formatter

### Frontend

- Use ES6+ modules
- Format with Prettier (2 spaces for HTML, 4 spaces for JS/CSS)
- Follow GOV.UK Design System patterns for UI components
- HTML templates use Jinja2 with GOV.UK Frontend Jinja macros

### Database

- Use SQLAlchemy 2.0+ ORM patterns (no direct model imports in most code)
- Access data through interfaces in `app.common.data.interfaces`
- Never import from `app.common.data.models` directly (except in interfaces and migrations)
- Write Alembic migrations for schema changes
- Use PostgreSQL-specific features where appropriate

## Architecture Patterns

### Layer Architecture

The application uses a layered architecture with strict import rules:

1. **Data Layer**: `app.common.data.models` - Database models (restricted access)
2. **Interface Layer**: `app.common.data.interfaces` - Data access interfaces
3. **Service Layer**: `app.services` - Business logic
4. **Route Layer**: `app.deliver_grant_funding.routes`, `app.access_grant_funding.routes` - HTTP endpoints
5. **Developer Tools**: `app.developers` - Development-only features (isolated from main app)

**Important**: Do NOT import models directly. Use interfaces defined in `app.common.data.interfaces`.

### Key Architectural Rules

- DB models should only be imported by interfaces and migrations
- The `developers` package is isolated and should not be imported by the main app
- Temporary interfaces (`app.common.data.interfaces.temporary`) are only for the `developers` package

## Testing Requirements

### Unit and Integration Tests

- Use pytest with fixtures from `tests/conftest.py`
- Test files: `tests/**/**/test_*.py`
- Run with: `uv run pytest` (excludes E2E by default)
- Use factories from `tests/factories.py` for test data
- Mock external services (e.g., Notify, SSO)

### End-to-End Tests

- Located in `tests/e2e/`
- Use Playwright with pytest
- Run with: `uv run pytest --e2e`
- One-time setup: `uv run playwright install`
- Use `authenticated_browser` fixture for logged-in tests
- SSO is stubbed locally via `stubs/sso/`

### Frontend Tests

- Use Vitest for JavaScript tests
- Test files in `app/assets/test/`
- Run with: `npm test`

## Common Commands

### Development

```bash
make bootstrap          # Initial setup (certs, pre-commit, vite)
make up                # Start app via docker-compose
make down              # Stop app
make build             # Rebuild docker image
```

### Testing

```bash
uv run pytest                      # Run unit/integration tests
uv run pytest --e2e               # Run E2E tests
uv run pytest --e2e --headed      # Run E2E tests with visible browser
npm test                          # Run frontend tests
```

### Linting and Formatting

```bash
uv run ruff check .               # Check Python code
uv run ruff format .              # Format Python code
uv run mypy app tests             # Type checking
make check-html                   # Check HTML formatting
make format-html                  # Format HTML templates
make format-css-js                # Format CSS and JavaScript
uv run pre-commit run --all-files # Run all pre-commit hooks
```

### Database

```bash
uv run flask db migrate -m "message"  # Create migration
uv run flask db upgrade              # Apply migrations
uv run flask developers seed-grants  # Load sample data
```

## Important Files and Locations

- **Config**: `app/config.py` - Environment-based configuration
- **Routes**: `app/deliver_grant_funding/routes/` - Main application routes
- **Templates**: `app/*/templates/` - Jinja2 templates
- **Models**: `app/common/data/models.py` - SQLAlchemy models
- **Interfaces**: `app/common/data/interfaces/` - Data access layer
- **Forms**: `app/common/forms/` - WTForms with GOV.UK styling
- **Frontend Assets**: `app/assets/` - JavaScript, CSS, images
- **Migrations**: `app/common/data/migrations/versions/` - Alembic migrations

## Special Considerations

### GOV.UK Patterns

- Use GOV.UK Design System components via `govuk-frontend-jinja` and `govuk-frontend-wtf`
- Follow GDS service patterns and accessibility guidelines (WCAG 2.1 AA)
- Use appropriate form validation and error messages per GDS patterns

### Security

- Never commit secrets or credentials
- Use Flask-Talisman for security headers
- Validate and sanitize all user inputs
- Use parameterized queries (SQLAlchemy does this by default)
- Follow secure authentication patterns (Microsoft SSO in production)

### Performance

- Watch for N+1 query problems (use SQLAlchemy eager loading)
- Add appropriate database indexes for queries
- Use Flask Debug Toolbar to profile queries in development

### Authentication and Authorization

- Authentication via Microsoft SSO (stubbed locally)
- Use `@login_required` decorator for protected routes
- Check user permissions before data access (add WHERE clauses based on user)
- Use `current_user` from Flask-Login

## Git Workflow

- Create feature branches from `main`
- Follow PR template in `.github/pull_request_template.md`
- Ensure pre-commit hooks pass before committing
- Write clear, descriptive commit messages
- Link PRs to Jira tickets or GitHub issues

## When Making Changes

1. **Before changing Python code**: Check import rules in `pyproject.toml` [tool.importlinter.contracts]
2. **Before changing models**: Create an Alembic migration
3. **Before changing templates**: Ensure GOV.UK patterns are followed
4. **Before changing routes**: Update tests and consider authorization
5. **Always**: Run relevant tests and linting before committing

## Useful Tips

- Local app runs at: https://funding.communities.gov.localhost:8080/
- Use `uv sync` to update dependencies after pulling changes
- Use `make clean-build` if encountering Docker cache issues
- Check `app/developers/commands.py` for useful Flask CLI commands
- The Flask Debug Toolbar is available in development mode
- Use factories in tests to avoid boilerplate data setup

## Resources

- [GOV.UK Design System](https://design-system.service.gov.uk/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [Playwright Python Documentation](https://playwright.dev/python/)
