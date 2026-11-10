"""初始建表：模型层是唯一事实来源，本 revision 直接 create_all。

revision = 0001_initial
"""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from src.config.database import Base
    import src.models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from src.config.database import Base
    import src.models  # noqa: F401

    Base.metadata.drop_all(bind=op.get_bind())
