from fastapi import Request, HTTPException, status
from app.core.security import verify_csrf_token, generate_csrf_token

CSRF_HEADER_NAME = "X-CSRF-Token"


def get_csrf_token_from_request(request: Request) -> str | None:
    return request.headers.get(CSRF_HEADER_NAME) or request.headers.get("x-csrf-token") or request.headers.get("X-XSRF-TOKEN")


def validate_csrf(request: Request):
    """
    Validate CSRF token for state-changing HTTP requests.
    Exempt safe methods (GET, HEAD, OPTIONS).
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # Check if request has an auth cookie (only cookie-authenticated requests require CSRF)
    from app.core.config import settings
    auth_cookie = request.cookies.get(settings.COOKIE_NAME)
    if not auth_cookie:
        return  # Public request, e.g. initial login/register

    token = get_csrf_token_from_request(request)
    if not token or not verify_csrf_token(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed. Missing or invalid X-CSRF-Token header."
        )
