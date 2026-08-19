"""add prdct_sno, update unique key

Revision ID: fcc2b06f6cfe
Revises: 64bcf84d6951
Create Date: 2026-08-19 03:44:35.021578

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcc2b06f6cfe'
down_revision: Union[str, Sequence[str], None] = '64bcf84d6951'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("delivery_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prdct_sno", sa.Integer(), nullable=False, server_default="0"))
        batch_op.drop_constraint("uq_delivery_request_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_delivery_request_identity", ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_sno"]
        )
        batch_op.alter_column("prdct_sno", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("delivery_requests", schema=None) as batch_op:
        batch_op.drop_constraint("uq_delivery_request_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_delivery_request_identity",
            ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_clsfc_nm", "dtl_prdct_nm"],
        )
        batch_op.drop_column("prdct_sno")
