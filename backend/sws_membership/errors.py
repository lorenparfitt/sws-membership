"""API error shapes shared by every router."""

from ninja import NinjaAPI
from ninja.errors import HttpError


class Refused(Exception):
    """A request that is well formed but not allowed, with reasons per item."""

    def __init__(self, reasons: dict[str, list[str]]) -> None:
        super().__init__("; ".join(f"{k}: {', '.join(v)}" for k, v in reasons.items()))
        self.reasons = reasons


def install_error_handlers(api: NinjaAPI) -> None:
    @api.exception_handler(Refused)
    def refused(request, exc: Refused):
        return api.create_response(request, {"detail": {"refused": exc.reasons}}, status=409)


__all__ = ["HttpError", "Refused", "install_error_handlers"]
