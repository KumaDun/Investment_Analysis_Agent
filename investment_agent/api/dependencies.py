from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from investment_agent.auth.service import AuthService
from investment_agent.auth.sessions import Session

bearer_schema = HTTPBearer(auto_error=False)

def get_auth_service(request: Request)  -> AuthService:
    return request.app.state.auth_service

def current_session(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_schema),
        services: AuthService = Depends(get_auth_service)
) -> Session:
    if credentials is not None:
        session = services.get_session(credentials.credentials)
        if session is not None:
            return session

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail = "Invalid or expired session"
    )