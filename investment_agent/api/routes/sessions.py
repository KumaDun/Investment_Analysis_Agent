from fastapi import APIRouter, HTTPException, Request, status, Depends

from investment_agent.api.schemas import LoginRequest, LoginResponse, SessionResponse, OKResponse
from investment_agent.auth.service import AuthService

from investment_agent.api.dependencies import current_session, get_auth_service
from investment_agent.auth.sessions import Session

router = APIRouter(tags=["sessions"])

@router.post("/login", response_model=LoginResponse)
async def login(request: Request, login_request: LoginRequest) -> LoginResponse:
    service: AuthService = request.app.state.auth_service
    session = service.login(login_request.username, login_request.password)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return LoginResponse(
        token=session.token,
        user_id=session.user_id,
        expires_at=session.expires_at,
    )

@router.get("/session", response_model=SessionResponse)
def get_session(session: Session = Depends(current_session)) -> SessionResponse:
    return SessionResponse(
        user_id=session.user_id,
        expires_at=session.expires_at,
    )

@router.delete("/session", response_model=OKResponse)
def logout(
        session: Session = Depends(current_session),
        service: AuthService = Depends(get_auth_service)
) -> OKResponse:
    service.logout(session.token)
    return OKResponse(ok=True)