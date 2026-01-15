---
name: git-commit
description: Helps write clear, conventional git commit messages following best practices. Use when the user asks to create a commit, write a commit message, or needs help with git commit formatting.
---

# Git Commit Message Writer

This skill helps you write clear, well-structured git commit messages following conventional commit format and best practices.

## Commit Message Format

Follow this structure:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type (required)
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, no logic change)
- **refactor**: Code refactoring (no feat/fix)
- **perf**: Performance improvements
- **test**: Adding or updating tests
- **chore**: Maintenance tasks (deps, config, etc.)
- **ci**: CI/CD changes
- **build**: Build system changes

### Scope (optional)
The scope indicates what part of the codebase is affected (e.g., api, auth, ui, parser).

### Subject (required)
- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter
- No period at the end
- Keep under 50 characters
- Be specific and clear

### Body (optional)
- Explain the "what" and "why", not the "how"
- Wrap at 72 characters
- Separate from subject with blank line

### Footer (optional)
- Breaking changes: `BREAKING CHANGE: <description>`
- Issue references: `Fixes #123` or `Closes #456`

## Examples

### Simple feature
```
feat(auth): add password reset functionality
```

### Bug fix with details
```
fix(parser): handle edge case with empty arrays

The parser was throwing an error when encountering empty
arrays in nested objects. Added validation to check array
length before processing.

Fixes #234
```

### Breaking change
```
refactor(api)!: change authentication endpoint structure

Updated /auth endpoints to use new token format for
improved security and consistency with OAuth2 standards.

BREAKING CHANGE: All API clients must update to use the
new /auth/token endpoint instead of /auth/login
```

## Guidelines

1. **Be concise but descriptive**: The subject should give a complete picture
2. **Focus on the why**: Explain motivation and context in the body
3. **One commit, one concern**: Each commit should represent a single logical change
4. **Use conventional commits**: This enables automated changelog generation
5. **Reference issues**: Link to issue tracker when applicable
6. **Mark breaking changes**: Always use `!` and `BREAKING CHANGE:` for breaking changes

## When to Use This Skill

- User asks to "create a commit" or "commit these changes"
- User asks for help writing a commit message
- User wants to review or improve a commit message
- You need to follow git commit best practices
