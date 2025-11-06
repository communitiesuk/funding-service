When reviewing code, focus on:

## Security Critical Issues
- Check for hardcoded secrets, API keys, or credentials in code and config files
- Look for SQL injection vulnerabilities (use parameterized queries, not f-strings)
- Verify proper input validation and sanitization, especially in web frameworks
- Review authentication and authorization decorators/middleware
- Check for unsafe pickle/eval usage and command injection risks

## Performance Red Flags
- Identify N+1 database query problems in SQLAlchemy use
- Spot inefficient loops and opportunities for list comprehensions or generators
- Review memory usage in data processing (prefer generators over large lists)
- Check for missing database indexes on frequently queried fields

## Code Quality Essentials
- Functions should follow single responsibility principle (typically < 20 lines)
- Use descriptive names following PEP 8 conventions (snake_case)
- Ensure proper exception handling with specific exception types
- Docstrings should document complex functions and classes

## Test Coverage
- Ensure new code has appropriate unit, integration, and e2e coverage
- Mock external dependencies appropriately
- Follow existing test patterns and fixture usage
- Aim for meaningful assertions, not just coverage numbers

## Review Style
- Be specific and actionable in feedback
- Explain the "why" behind recommendations
- Acknowledge good patterns and Pythonic solutions
- Ask clarifying questions when code intent is unclear
- Don't comment on formatting and linting that would be automatically handled by our pre-commit hooks and PR checks

Always prioritize security vulnerabilities and performance issues that could impact users.

Always suggest changes to improve readability. For example, this suggestion makes the code more readable, testable, and follows Python conventions:

# Instead of:
if user.get('email') and '@' in user.get('email', '') and len(user.get('email', '')) > 5:
    submit_button['enabled'] = True
else:
    submit_button['enabled'] = False

# Consider:
def is_valid_email(email: str) -> bool:
    """Validate email has basic required format."""
    return bool(
        email
        and '@' in email
        and len(email) > 5
    )

submit_button['enabled'] = is_valid_email(user.get('email', ''))
