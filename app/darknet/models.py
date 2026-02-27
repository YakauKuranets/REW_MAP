# -*- coding: utf-8 -*-
"""Модели данных для постов и найденных утечек в darknet-источниках."""

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


class DarknetPost(db.Model):
    """Пост из darknet-источника, который может содержать утечку данных."""

    __tablename__ = "darknet_posts"

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(1024), nullable=True)
    title = db.Column(db.String(512), nullable=True)
    content = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(255), nullable=True)
    indicators = db.Column(db.JSON)
    discovered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    analyzed = db.Column(db.Boolean, default=False)
    analysis_result = db.Column(db.JSON)
    risk_score = db.Column(db.Integer, default=0)


class LeakedCredential(db.Model):
    """Обнаруженные учетные данные, извлеченные из постов и дампов."""

    __tablename__ = "leaked_credentials"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("darknet_posts.id"), nullable=True)
    email = db.Column(db.String(320), nullable=True, index=True)
    domain = db.Column(db.String(255), nullable=True, index=True)
    username = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(512), nullable=True)
    discovered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    post = db.relationship("DarknetPost", backref=db.backref("credentials", lazy="dynamic"))
