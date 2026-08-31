class ContractValidationError(ValueError):
    """Raised when runtime data violates the frozen V3 contract."""


class ProviderError(RuntimeError):
    """Base class for model Provider failures safe to surface to callers."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.error_code = error_code


class ProviderConfigurationError(ProviderError):
    """Raised before a request when Provider configuration is unsafe or incomplete."""


class ProviderBadRequestError(ProviderError):
    """Raised for request shape or parameter errors that should not be retried."""


class ProviderAuthenticationError(ProviderError):
    """Raised when the Provider rejects the configured credential."""


class ProviderInsufficientBalanceError(ProviderError):
    """Raised when the Provider account has insufficient balance."""


class ProviderRateLimitError(ProviderError):
    """Raised after bounded retries for Provider rate limiting."""


class ProviderTransientError(ProviderError):
    """Raised after bounded retries for network or upstream server failures."""


class ProviderResponseError(ProviderError):
    """Raised when a successful HTTP response violates the Provider response contract."""
