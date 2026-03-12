from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ErrorDefinition:
    code: str
    message: str
    retryable: bool = False


ERRORS = {
    "provider_not_supported": ErrorDefinition("provider_not_supported", "Unsupported provider."),
    "queue_timeout": ErrorDefinition("queue_timeout", "Timed out waiting for execution slot.", True),
    "browser_unavailable": ErrorDefinition("browser_unavailable", "Browser startup failed.", True),
    "cdp_unreachable": ErrorDefinition("cdp_unreachable", "CDP endpoint is unreachable.", True),
    "master_profile_missing": ErrorDefinition("master_profile_missing", "Master profile directory is missing."),
    "profile_locked": ErrorDefinition("profile_locked", "Browser profile is locked or unavailable.", True),
    "runtime_profile_copy_failed": ErrorDefinition("runtime_profile_copy_failed", "Failed to prepare runtime profile.", True),
    "login_required": ErrorDefinition("login_required", "Provider login state is invalid."),
    "page_navigation_failed": ErrorDefinition("page_navigation_failed", "Provider page navigation failed.", True),
    "page_not_ready": ErrorDefinition("page_not_ready", "Provider page is not ready for interaction.", True),
    "selector_not_found": ErrorDefinition("selector_not_found", "Required page selector was not found.", True),
    "send_failed": ErrorDefinition("send_failed", "Failed to submit prompt to provider.", True),
    "provider_timeout": ErrorDefinition("provider_timeout", "Timed out waiting for provider response.", True),
    "extract_empty": ErrorDefinition("extract_empty", "Provider returned an empty response.", True),
    "provider_error": ErrorDefinition("provider_error", "Provider execution failed.", True),
}


class AdapterError(Exception):
    def __init__(
        self,
        error_key: str,
        *,
        detail: str | None = None,
        provider: str | None = None,
    ) -> None:
        self.definition = ERRORS[error_key]
        self.error_key = error_key
        self.detail = detail
        self.provider = provider
        super().__init__(self.definition.message)
