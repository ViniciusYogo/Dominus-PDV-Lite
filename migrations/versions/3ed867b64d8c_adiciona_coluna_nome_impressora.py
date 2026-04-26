"""Adiciona coluna nome_impressora

Revision ID: 3ed867b64d8c
Revises: 
Create Date: 2026-04-20 10:20:35.315978

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3ed867b64d8c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Adiciona APENAS a coluna nova da impressora, ignorando o resto
    with op.batch_alter_table('configuracao', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nome_impressora', sa.String(length=100), nullable=True))

def downgrade():
    # Remove APENAS a coluna da impressora caso a gente precise reverter
    with op.batch_alter_table('configuracao', schema=None) as batch_op:
        batch_op.drop_column('nome_impressora')