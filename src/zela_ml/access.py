import secrets
import time
from threading import Lock

from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "zela_equipe"
VISITOR_COOKIE = "zela_visitante"
SESSION_SECONDS = 8 * 60 * 60


class TeamAccess:
    def __init__(self, password: str | None):
        self.password = password
        self.sessions: dict[str, float] = {}
        self.lock = Lock()

    def authorized(self, request: Request) -> bool:
        token = request.cookies.get(SESSION_COOKIE, "")
        with self.lock:
            return self.sessions.get(token, 0) > time.monotonic()

    def require(self, request: Request) -> None:
        if not self.authorized(request):
            raise HTTPException(401, "Entre com o acesso da equipe.")

    def login(self, password: str, request: Request, response: Response) -> None:
        if not self.password:
            raise HTTPException(503, "O acesso da equipe precisa ser configurado.")
        if not secrets.compare_digest(password.encode(), self.password.encode()):
            raise HTTPException(401, "A senha informada está incorreta.")
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self.lock:
            self.sessions = {key: end for key, end in self.sessions.items() if end > now}
            self.sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
            self.sessions[token] = now + SESSION_SECONDS
        set_cookie(request, response, SESSION_COOKIE, token, SESSION_SECONDS)

    def logout(self, request: Request, response: Response) -> None:
        with self.lock:
            self.sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
        response.delete_cookie(SESSION_COOKIE)


def set_cookie(request: Request, response: Response, name: str, value: str, age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=age,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def visitor(request: Request, response: Response) -> str:
    token = request.cookies.get(VISITOR_COOKIE, "")
    if len(token) != 32 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in token):
        token = secrets.token_urlsafe(24)
        set_cookie(request, response, VISITOR_COOKIE, token, 365 * 24 * 60 * 60)
    return token
