# SECURITY.md - Django Micboard Public Repository

> **This is a public open-source project.** Protecting sensitive information is critical for the security of all users.

## Quick Security Rules

✅ **DO**:
- Use `.env.local` for any local configuration (this file is in `.gitignore`)
- Reference configuration via environment variables
- Use `.env.example` as a template
- Keep VPN device IPs in `.env.local`, not in code
- Review `.gitignore` before committing
- Check for secrets in `git diff` before committing

❌ **DON'T**:
- Commit `.env.local` or any `.env` file with real values
- Hardcode API keys, shared keys, or passwords
- Include device IP addresses in source code
- Store authentication credentials in Python files
- Commit database files (`*.sqlite3`)
- Add company-specific paths or domain names
- Include screenshots with sensitive information

## Files That Should NEVER Be Committed

These are in `.gitignore` and automatically excluded:

```
.env.local              # Local configuration
.env.*.local            # Environment-specific configs
*.key, *.pem            # SSL certificates
sharedkey.txt           # Shure API authentication
device_inventory*.json  # Device discovery manifests
db.sqlite3              # Local database
scripts/local_*.py      # Local test scripts
```

## Before You Push

1. **Check for secrets**:
   ```bash
   git diff HEAD | grep -i "secret\|key\|password\|token\|api"
   ```

2. **Verify .env files**:
   ```bash
   git ls-files | grep "\.env\."
   ```

3. **Review your changes**:
   ```bash
   git diff --cached
   ```

4. **Never force push**:
   ```bash
   # ❌ WRONG
   git push --force

   # ✅ RIGHT (if needed)
   git push --force-with-lease
   ```

## If You Accidentally Commit a Secret

**Immediately**:

1. Revoke/rotate the credential (e.g., regenerate API key)
2. Remove from git history:
   ```bash
   # For recent commits on your branch
   git filter-branch --tree-filter 'rm -f <file>' HEAD
   git push --force-with-lease
   ```
3. Report to the maintainers if on shared branch

## Using VPN Device IPs

VPN device IP addresses are sensitive infrastructure information:

1. **Store locally only**:
   ```bash
   # ✅ GOOD - in .env.local (not committed)
   SHURE_DEVICE_IPS=172.21.1.100,172.21.1.101

   # ❌ BAD - in Python source code
   DEVICE_IPS = ["172.21.1.100", "172.21.1.101"]
   ```

2. **Document in issues/PRs carefully**:
   - Don't include actual IP addresses
   - Use "VPN device testing" as generic reference
   - Never screenshot network diagnostics with IPs visible

3. **Device discovery manifests**:
   - `device_manifest.json` is created locally, not committed
   - Contains device discovery results
   - Never share this file publicly

## Environment Variables

All configuration should use environment variables:

```python
# ✅ CORRECT - Load from environment
import os

SHURE_API_KEY = os.environ.get('SHURE_API_KEY')
DEVICE_IPS = os.environ.get('SHURE_DEVICE_IPS', '').split(',')

# ❌ WRONG - Hardcoded
SHURE_API_KEY = "my-secret-key"
DEVICE_IPS = ["172.21.1.100"]
```

## Documentation Guidelines

For contributing documentation:

1. **Use `.env.example` as template** - Show all variables, no real values
2. **Generic examples** - Use "your-value-here" instead of real values
3. **Security notes** - Add ⚠️ warnings for sensitive configurations
4. **Reference docs/CONFIGURATION.md** - Direct readers to configuration guide

Example:
```markdown
# ❌ WRONG
Set SHURE_SHARED_KEY=abc123xyz in your shell

# ✅ CORRECT
Set SHURE_SHARED_KEY to your Shure shared key in `.env.local`:
```
SHURE_SHARED_KEY=your-actual-shared-key
```
See [Configuration Guide](docs/CONFIGURATION.md) for details.
```

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. **DO NOT** commit the vulnerable code
3. **DO** report privately to maintainers
4. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

## Company Information Protection

This project must NOT expose:

- Internal IP addresses or network topology
- Company domain names or internal services
- Employee names or organizational structure
- Device locations or deployment details
- Proprietary device configurations
- Internal documentation or policies

When in doubt, **ask the maintainers**.

## CI/CD Security

For automated testing with sensitive data:

1. **Store secrets in CI/CD platform** (GitHub Secrets, GitLab Secrets, etc.)
2. **Never log secrets**:
   ```bash
   # ❌ WRONG
   echo "DEBUG: API_KEY=$API_KEY"

   # ✅ CORRECT
   echo "DEBUG: API_KEY is configured"
   ```
3. **Use masked output**:
   - GitHub: `::add-mask::$SECRET`
   - GitLab: Add `[masked]` tag
4. **Rotate credentials regularly** - Regenerate keys after exposure

## Examples of What NOT to Share

❌ Screenshots showing:
- IP addresses
- Device serial numbers
- Shared keys or API tokens
- Internal domain names
- Wi-Fi SSIDs or passwords

❌ Debug output containing:
- Full HTTP headers with auth tokens
- Database connection strings with passwords
- Environment variables
- API responses with credentials

❌ Repository content containing:
- Hardcoded configuration
- Test data with real devices
- Database backups
- Log files

## More Information

- [Configuration Guide](docs/CONFIGURATION.md) - Secure configuration
- [VPN Device Population](docs/VPN_DEVICE_POPULATION.md) - Safe device testing
- [Public Repo Setup](PUBLIC_REPO_SECURITY.md) - Security implementation details
- [Contributing Guide](CONTRIBUTING.md) - Development guidelines

## Questions?

If you're unsure whether something should be committed:

1. Check if it's in `.gitignore` - if so, it shouldn't be committed
2. Does it contain any credentials? - if yes, don't commit it
3. Would you want this visible to everyone on GitHub? - if no, don't commit it
4. When in doubt, **ask maintainers** before committing

---

**Remember**: The security of this project depends on every contributor. When in doubt, err on the side of caution.

**Last Updated**: 2025-01-15
**Status**: Active - Security measures in place
