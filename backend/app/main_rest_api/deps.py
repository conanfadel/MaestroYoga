"""Shared imports for REST API route modules (supports package vs script execution)."""

from __future__ import annotations

try:
    from .. import models, schemas
    from ..booking_utils import count_active_bookings
    from ..database import get_db
    from ..payments import (
        PaymobPaymentProvider,
        StripePaymentProvider,
        get_payment_provider,
        payment_provider_supports_hosted_checkout,
    )
    from ..security import (
        create_access_token,
        get_current_user,
        hash_password,
        require_any_permission,
        require_permissions,
        require_roles,
        verify_password,
    )
    from ..tenant_utils import require_user_center_id
    from ..time_utils import utcnow_naive
except ImportError:
    from backend.app import models, schemas
    from backend.app.booking_utils import count_active_bookings
    from backend.app.database import get_db
    from backend.app.payments import (
        PaymobPaymentProvider,
        StripePaymentProvider,
        get_payment_provider,
        payment_provider_supports_hosted_checkout,
    )
    from backend.app.security import (
        create_access_token,
        get_current_user,
        hash_password,
        require_any_permission,
        require_permissions,
        require_roles,
        verify_password,
    )
    from backend.app.tenant_utils import require_user_center_id
    from backend.app.time_utils import utcnow_naive
