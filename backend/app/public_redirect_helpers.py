from fastapi.responses import RedirectResponse

from .web_shared import _url_with_params


def redirect_public_index_with_msg(*, center_id: int, msg: str, status_code: int = 303) -> RedirectResponse:
    return redirect_public_index_with_params(center_id=center_id, msg=msg, status_code=status_code)


def redirect_public_index_with_params(*, center_id: int, msg: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(
        url=_url_with_params("/index", center_id=str(center_id), msg=msg),
        status_code=status_code,
    )


def redirect_public_index_paid_mock(
    *,
    center_id: int,
    booking_id: int | str,
    status_code: int = 303,
) -> RedirectResponse:
    return RedirectResponse(
        url=_url_with_params("/index", center_id=str(center_id), msg="paid_mock", booking_id=str(booking_id)),
        status_code=status_code,
    )
