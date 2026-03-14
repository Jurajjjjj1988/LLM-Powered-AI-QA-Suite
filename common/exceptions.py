class QASuiteError(Exception):
    """Base exception for the QA Suite."""

class ConfigurationError(QASuiteError):
    """Raised when configuration is invalid or missing."""

class ClaudeAPIError(QASuiteError):
    """Raised when Claude API call fails after all retries."""

class ValidationError(QASuiteError):
    """Raised when output validation fails."""

class DatabaseError(QASuiteError):
    """Raised on database operation failure."""

class SanitizationError(QASuiteError):
    """Raised when input fails sanitization."""
