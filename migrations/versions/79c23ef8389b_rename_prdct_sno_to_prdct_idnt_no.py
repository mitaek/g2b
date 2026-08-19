"""rename prdct_sno to prdct_idnt_no

Revision ID: 79c23ef8389b
Revises: fcc2b06f6cfe
Create Date: 2026-08-19 04:10:45.730200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79c23ef8389b'
down_revision: Union[str, Sequence[str], None] = 'fcc2b06f6cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    prdct_sno(물품순번)와 prdct_idnt_no(물품식별번호)는 값의 의미 자체가 다른
    필드라 값을 이관하지 않고 새 컬럼으로 교체합니다 (수집 대상 API를 변경하며
    natural key도 함께 변경됨).
    """
    with op.batch_alter_table("delivery_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prdct_idnt_no", sa.Integer(), nullable=False, server_default="0"))
        batch_op.drop_constraint("uq_delivery_request_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_delivery_request_identity", ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_idnt_no"]
        )
        batch_op.alter_column("prdct_idnt_no", server_default=None)
        batch_op.drop_column("prdct_sno")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("delivery_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prdct_sno", sa.Integer(), nullable=False, server_default="0"))
        batch_op.drop_constraint("uq_delivery_request_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_delivery_request_identity", ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_sno"]
        )
        batch_op.alter_column("prdct_sno", server_default=None)
        batch_op.drop_column("prdct_idnt_no")
