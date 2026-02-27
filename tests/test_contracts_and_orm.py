from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.types import JSON

from app.schemas import IncidentCreateSchema, TelemetryCreateSchema


Base = declarative_base()


class _Event(Base):
    __tablename__ = 'events_mutable_test'

    id = Column(Integer, primary_key=True)
    payload = Column(MutableDict.as_mutable(JSON), nullable=True)


def _validate_incident_like_route(payload: dict):
    try:
        IncidentCreateSchema.model_validate(payload)
        return {'ok': True}, 200
    except ValidationError as e:
        return {'error': 'Validation failed', 'details': e.errors()}, 400


def test_incident_contract_broken_payload_maps_to_400():
    body, status = _validate_incident_like_route(
        {
            'title': 'bad',
            'description': 'broken level',
            'level': 999,  # invalid: must be 1..5
            'location': 'test',
        }
    )

    assert status == 400
    assert body['error'] == 'Validation failed'
    assert isinstance(body['details'], list)


def test_telemetry_contract_rejects_invalid_coordinates():
    with pytest.raises(ValidationError):
        TelemetryCreateSchema.model_validate(
            {
                'lon': 30,
                'lat': 120,  # invalid latitude
                'alt': 100,
                'battery': 80,
                'status': 'start',
                'user_id': '1001',
            }
        )


def test_mutabledict_tracks_nested_updates_after_commit():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        row = _Event(payload={'status': 'new'})
        session.add(row)
        session.commit()

        row.payload['status'] = 'resolved'
        session.commit()
        session.refresh(row)

        assert row.payload['status'] == 'resolved'
