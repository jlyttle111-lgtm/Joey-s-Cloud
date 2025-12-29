# Development Guidelines
## Joey's Cloud - Code Standards & Best Practices

## 🎯 Project Principles

1. **Security First**: Always validate inputs, use parameterized queries, hash passwords
2. **User Isolation**: Never allow one user to access another user's files
3. **Path Safety**: Always use `safe_join()` and `sanitize_relpath()` for file operations
4. **Error Handling**: Provide meaningful error messages without exposing internals
5. **Simplicity**: Keep code readable and maintainable (single-file is fine for now)

---

## 📝 Code Style

### Python Standards
- Follow PEP 8 (use `black` or `autopep8` if desired)
- Use descriptive variable names
- Add docstrings for functions (especially public APIs)
- Maximum line length: 100-120 characters

### Function Naming
- Routes: `route_name()` or `api_endpoint()`
- Helpers: `verb_noun()` e.g., `sanitize_path()`, `ensure_storage()`
- Database: `get_user()`, `create_user()`

### Variable Naming
- Use `snake_case` for functions and variables
- Use `UPPER_CASE` for constants
- Prefix private helpers with `_` if needed (though not enforced)

---

## 🔒 Security Guidelines

### Always:
1. ✅ Sanitize all file paths with `sanitize_relpath()` and `safe_join()`
2. ✅ Use parameterized SQL queries (you're already doing this!)
3. ✅ Hash passwords with `generate_password_hash()`
4. ✅ Validate user input (username length, password strength)
5. ✅ Check authentication before file operations
6. ✅ Use environment variables for secrets

### Never:
1. ❌ Trust user-provided file paths directly
2. ❌ Expose database errors to users
3. ❌ Store passwords in plain text
4. ❌ Run with `debug=True` in production
5. ❌ Commit `.env` files or database files
6. ❌ Allow directory traversal (`../` attacks)

---

## 🗂️ File Organization

### Current Structure (Single File)
```
app.py              # Main application (routes, helpers, HTML)
requirements.txt    # Dependencies
.env.example        # Environment template
.gitignore         # Git exclusions
README.md          # Documentation
CODE_REVIEW.md     # This review
GUIDELINES.md      # These guidelines
```

### Future Structure (If Growing)
```
app/
├── __init__.py
├── routes/
│   ├── auth.py
│   ├── files.py
│   └── api.py
├── models/
│   └── user.py
├── utils/
│   ├── storage.py
│   └── security.py
└── templates/
    └── app.html
```

---

## 🧪 Testing Guidelines

### What to Test
1. **Authentication**
   - Valid login/logout
   - Invalid credentials
   - Session persistence

2. **File Operations**
   - Upload (single and folder)
   - Download
   - Delete
   - Rename
   - Path traversal attempts

3. **Security**
   - Unauthorized access attempts
   - Path sanitization
   - SQL injection attempts (should fail)

4. **Edge Cases**
   - Empty uploads
   - Very long filenames
   - Special characters in paths
   - Concurrent uploads

### Test Structure (Future)
```python
# tests/test_auth.py
def test_login_valid():
    # Test valid login

def test_login_invalid():
    # Test invalid credentials

# tests/test_files.py
def test_upload_single():
    # Test single file upload

def test_path_traversal():
    # Test ../ attack prevention
```

---

## 📊 Database Guidelines

### Current Schema
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    pass_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
```

### Best Practices
1. Always use transactions for multi-step operations
2. Close connections explicitly (or use context managers)
3. Use `sqlite3.Row` for dictionary-like access
4. Add indexes for frequently queried columns (if needed)

### Future Schema Considerations
- `created_at` as TEXT with ISO format (easier debugging)
- Add `updated_at` timestamp
- Add `last_login` for security tracking
- Consider soft deletes (`deleted_at` column)

---

## 🗄️ Storage Guidelines

### Directory Structure
```
storage/
└── user_{id}/
    ├── folder1/
    │   └── file.txt
    └── file2.txt
```

### Rules
1. Each user gets isolated `user_{id}` directory
2. Use `sanitize_relpath()` for all user-provided paths
3. Use `safe_join()` to prevent directory traversal
4. Create directories with `os.makedirs(path, exist_ok=True)`
5. Never allow direct access outside user root

### File Naming
- Use `secure_filename()` from Werkzeug
- Preserve original extension when possible
- Handle duplicate names (consider adding timestamp)

---

## 🔌 API Guidelines

### Response Format
```json
{
  "ok": true,
  "msg": "Operation succeeded",
  "data": { ... }  // Optional
}
```

### Error Responses
```json
{
  "ok": false,
  "msg": "Human-readable error message"
}
```

### HTTP Status Codes
- `200`: Success
- `400`: Bad Request (invalid input)
- `401`: Unauthorized (not logged in)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `413`: Payload Too Large
- `409`: Conflict (duplicate resource)
- `500`: Internal Server Error

### Endpoint Naming
- RESTful: `/api/resource` (GET, POST, PUT, DELETE)
- Actions: `/api/resource/action` (POST)
- Current pattern is fine: `/api/upload`, `/api/delete`

---

## 🎨 Frontend Guidelines

### Current Approach
- Embedded HTML/CSS/JS in Python strings
- Single-page application (SPA-like)
- Vanilla JavaScript (no frameworks)

### If Expanding:
- Extract HTML to separate template files
- Consider using Jinja2 templates (Flask default)
- Or keep embedded if staying simple

### JavaScript Style
- Use modern ES6+ features
- Functions: `camelCase`
- Constants: `UPPER_SNAKE_CASE`
- Error handling: Always use try/catch for API calls

---

## 📝 Documentation Standards

### Code Comments
```python
# Good: Explains why, not what
# Use parameterized query to prevent SQL injection
cur.execute("SELECT * FROM users WHERE id=?", (uid,))

# Avoid: Stating the obvious
# Execute SQL query
cur.execute(...)
```

### Function Docstrings
```python
def safe_join(root: str, rel_path: str) -> str:
    """
    Safely join root directory with relative path, preventing directory traversal.
    
    Args:
        root: Absolute path to root directory
        rel_path: User-provided relative path
        
    Returns:
        Absolute path if valid
        
    Raises:
        ValueError: If path attempts to escape root directory
    """
```

---

## 🚀 Deployment Checklist

### Pre-Deployment
- [ ] All secrets in environment variables
- [ ] Debug mode disabled
- [ ] Tested all features
- [ ] Backup strategy in place
- [ ] Logging configured
- [ ] Error handling tested

### Post-Deployment
- [ ] Health check working
- [ ] Monitoring alerts set up
- [ ] Backups running
- [ ] SSL certificate valid
- [ ] Firewall rules configured
- [ ] Documentation updated

---

## 🔄 Version Control

### Commit Messages
Use clear, descriptive messages:
```
✅ "Add rate limiting to login endpoint"
✅ "Fix path traversal vulnerability in upload"
❌ "fixes"
❌ "update"
```

### Branch Strategy (If Using)
- `main`: Production-ready code
- `develop`: Development branch
- `feature/name`: New features
- `fix/name`: Bug fixes

---

## 📈 Performance Guidelines

### Current Optimizations
- Chunked uploads for large folders
- Streaming file downloads
- Minimal database queries

### Future Considerations
- Cache file tree (with TTL)
- Database connection pooling
- Background jobs for heavy operations
- CDN for static assets (if needed)

---

## 🐛 Debugging Guidelines

### Logging
```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Detailed info for debugging")
logger.info("General information")
logger.warning("Something unexpected but handled")
logger.error("Error that needs attention")
logger.critical("System-level issue")
```

### Debug Mode
- **Development**: `FLASK_DEBUG=true` (shows detailed errors)
- **Production**: `FLASK_DEBUG=false` (generic error messages)

---

## ✅ Code Review Checklist

Before committing:
- [ ] Code follows style guidelines
- [ ] Security checks passed (path sanitization, SQL injection)
- [ ] Error handling in place
- [ ] No hardcoded secrets
- [ ] Comments explain complex logic
- [ ] Tested manually (at minimum)

---

## 📚 Resources

### Flask
- Official Docs: https://flask.palletsprojects.com/
- Security: https://flask.palletsprojects.com/en/latest/security/

### Security
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- Secure Coding: https://cheatsheetseries.owasp.org/

### Python
- PEP 8: https://pep8.org/
- Best Practices: https://docs.python-guide.org/

---

**Last Updated**: 2025-01-26
**Maintainer**: Joey

