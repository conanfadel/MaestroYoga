"""Baseline revision — existing installs rely on init_db(); use Alembic for forward-only schema changes."""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
