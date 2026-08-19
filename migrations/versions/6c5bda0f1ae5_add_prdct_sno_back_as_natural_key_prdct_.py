"""add prdct_sno back as natural key, prdct_idnt_no informational

Revision ID: 6c5bda0f1ae5
Revises: 79c23ef8389b
Create Date: 2026-08-19 23:40:10.891028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c5bda0f1ae5'
down_revision: Union[str, Sequence[str], None] = '79c23ef8389b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    물품식별번호(prdct_idnt_no)는 한 납품요구 안에서 같은 상품이 서로 다른
    줄(물품순번)로 중복 발주될 수 있어 자연키로 쓸 수 없음이 확인됨(실제 데이터
    사례로 검증). 물품순번(prdct_sno)을 자연키로 되돌리고, prdct_idnt_no는
    정보용 컬럼으로 남긴다.
    """
    with op.batch_alter_table("delivery_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prdct_sno", sa.Integer(), nullable=False, server_default="0"))
        batch_op.alter_column("prdct_sno", server_default=None)
        batch_op.alter_column("prdct_idnt_no", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_constraint("uq_delivery_request_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_delivery_request_identity", ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_sno"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("delivery_requests", schema=None) as batch_op:
        batch_op.drop_constraint("uq_delivery_request_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_delivery_request_identity", ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_idnt_no"]
        )
        batch_op.alter_column("prdct_idnt_no", existing_type=sa.Integer(), nullable=False, server_default="0")
        batch_op.alter_column("prdct_idnt_no", server_default=None)
        batch_op.drop_column("prdct_sno")
