import os

import pytest
from sqlalchemy import func

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import PendingMarker


@pytest.mark.skipif(not os.environ.get('POSTGIS_TEST_DATABASE_URL'), reason='POSTGIS_TEST_DATABASE_URL is not configured')
def test_postgis_st_dwithin_filters_points_within_1km(monkeypatch):
    monkeypatch.setenv('DATABASE_URI', os.environ['POSTGIS_TEST_DATABASE_URL'])
    app = create_app(TestingConfig)

    with app.app_context():
        db.drop_all()
        db.create_all()

        points = [
            ('A', 55.751244, 37.618423),
            ('B', 55.757000, 37.615000),
            ('C', 55.760500, 37.620500),
            ('D', 55.730000, 37.640000),
            ('E', 55.700000, 37.500000),
        ]
        for name, lat, lon in points:
            db.session.add(PendingMarker(name=name, lat=lat, lon=lon, status='new'))
        db.session.commit()

        center_lon, center_lat = 37.618423, 55.751244
        center = func.ST_SetSRID(func.ST_MakePoint(center_lon, center_lat), 4326)

        names = [
            row.name
            for row in db.session.query(PendingMarker)
            .filter(func.ST_DWithin(PendingMarker.geom, center, 0.01))
            .order_by(PendingMarker.name)
            .all()
        ]

        assert names == ['A', 'B', 'C']
