"""Independent ranked queue, seasonal ratings, match settlement and honors."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_119'
down_revision = '20261016_118'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mistrealm_players',sa.Column('queue_mode',sa.String(12),nullable=False,server_default='casual'))
    op.add_column('mistrealm_players',sa.Column('ranked_reward_season',sa.Integer()))
    op.create_table('mistrealm_seasons',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=False),
        sa.Column('starts_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('ends_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('finalized_at',sa.DateTime(timezone=True)))
    op.create_index('ix_mistrealm_seasons_ends_at','mistrealm_seasons',['ends_at'])
    op.create_table('mistrealm_ratings',
        sa.Column('season_id',sa.Integer(),sa.ForeignKey('mistrealm_seasons.id'),primary_key=True),
        sa.Column('player_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),primary_key=True),
        sa.Column('rating',sa.Integer(),nullable=False),sa.Column('peak',sa.Integer(),nullable=False),
        sa.Column('wins',sa.Integer(),nullable=False),sa.Column('losses',sa.Integer(),nullable=False),
        sa.Column('draws',sa.Integer(),nullable=False),sa.Column('played_at',sa.DateTime(timezone=True)),
        sa.Column('reward_tier',sa.String(16)))
    op.create_index('ix_mistrealm_ratings_standing','mistrealm_ratings',['season_id','rating','wins'])
    op.create_table('mistrealm_ranked_matches',
        sa.Column('match_id',sa.Uuid(),primary_key=True),
        sa.Column('room_id',sa.Uuid(),sa.ForeignKey('mistrealm_rooms.id'),nullable=False,unique=True),
        sa.Column('season_id',sa.Integer(),sa.ForeignKey('mistrealm_seasons.id'),nullable=False),
        sa.Column('player_a',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('player_b',sa.Uuid(),sa.ForeignKey('mistrealm_players.id')),
        sa.Column('rating_a',sa.Integer(),nullable=False),sa.Column('rating_b',sa.Integer(),nullable=False),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('finished_at',sa.DateTime(timezone=True)),sa.Column('result',sa.JSON()))
    op.create_index('ix_mistrealm_ranked_matches_season_id','mistrealm_ranked_matches',['season_id'])
    op.create_index('ix_mistrealm_ranked_matches_finished_at','mistrealm_ranked_matches',['finished_at'])


def downgrade():
    op.drop_table('mistrealm_ranked_matches')
    op.drop_table('mistrealm_ratings')
    op.drop_table('mistrealm_seasons')
    op.drop_column('mistrealm_players','ranked_reward_season')
    op.drop_column('mistrealm_players','queue_mode')
