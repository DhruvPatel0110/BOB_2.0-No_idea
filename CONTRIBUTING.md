# Contributing to BOB 2.0 / PRISM

Thank you for contributing to the PRISM AI Code Review Coach ecosystem.
Please adhere to the following project conventions and standards.

---

## 1. Security & Data Protection

### §1.1 SQL Queries and Injection Prevention
- **Strict Rule:** Raw string interpolation (`f"SELECT ... {var}"`) in database queries is strictly prohibited.
- **Requirement:** Always use parameterized queries, prepared statements, or ORM query builders to ensure values are properly escaped.
- **Reference:** OWASP Top-10 A03:2021 Injection.

### §1.2 Secrets and Token Handling
- Never hardcode API keys, personal access tokens, or credentials in source files.
- All secrets must be loaded from environment variables using `os.getenv()`.

---

## 2. Code Quality & Logic Safety

### §2.1 Dictionary and Object Key Access
- Avoid direct chained key lookups on unvalidated dictionaries (e.g. `user["profile"]["name"]`) which can raise unhandled `KeyError` or `TypeError` exceptions.
- Prefer `.get()` with sensible defaults or explicit guard clauses:
  ```python
  profile = user.get("profile") or {}
  name = profile.get("name", "Unknown")
  ```

### §2.2 Error Handling & Clean Returns
- Functions must handle edge cases gracefully and return predictable types.
- Avoid bare `except:` blocks; catch specific exceptions.

---

## 3. Style & Documentation

### §3.1 Type Annotations
- All new function signatures must include Python type hints for parameters and return types.

### §3.2 Maintainability & Dead Code
- Unused variables, unreferenced imports, and dead code blocks must be removed prior to opening a Pull Request.

---

## 4. Test Coverage

### §4.1 Testing Requirements
- Every new feature, endpoint, or utility must be accompanied by automated unit tests.
