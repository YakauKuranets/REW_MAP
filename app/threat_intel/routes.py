# -*- coding: utf-8 -*-
"""
API для управления анализом утечек и получения результатов.
"""

from flask import Blueprint, request, jsonify
import asyncio
from app.auth.decorators import jwt_or_api_required
from app.threat_intel.leak_analyzer import LeakAnalyzer
from app.darknet.models import DarknetPost
from app.extensions import db
from app.analytics.relation_engine import graph_db
from app.threat_intel.asset_risk_graph import enrich_asset_risk
import logging

logger = logging.getLogger(__name__)
threat_bp = Blueprint('threat_intel', __name__, url_prefix='/threat-intel')


@threat_bp.route('/analyze-post/<int:post_id>', methods=['POST'])
@jwt_or_api_required
def analyze_post(post_id):
    """
    Анализирует конкретный пост.
    """
    post = DarknetPost.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    analyzer = LeakAnalyzer()
    result = analyzer.analyze_post(post)

    return jsonify(result)


@threat_bp.route('/analyze-pending', methods=['POST'])
@jwt_or_api_required
def analyze_pending():
    """
    Анализирует все необработанные посты.
    """
    posts = DarknetPost.query.filter_by(analyzed=False).limit(100).all()
    analyzer = LeakAnalyzer()
    results = analyzer.analyze_batch(posts)

    # Помечаем посты как обработанные
    for post in posts:
        post.analyzed = True
    db.session.commit()

    return jsonify({
        'processed': len(results),
        'results': results
    })


@threat_bp.route('/statistics', methods=['GET'])
@jwt_or_api_required
def get_statistics():
    """
    Возвращает статистику по утечкам.
    """
    hours = request.args.get('hours', 24, type=int)
    analyzer = LeakAnalyzer()
    stats = analyzer.get_statistics(hours)
    return jsonify(stats)


@threat_bp.route('/check-target/<target>', methods=['GET'])
@jwt_or_api_required
def check_target(target):
    """
    Проверяет, появлялся ли целевой email/домен в утечках.
    """
    from app.darknet.models import LeakedCredential

    results = LeakedCredential.query.filter(
        (LeakedCredential.email == target) | (LeakedCredential.domain == target)
    ).all()

    return jsonify({
        'target': target,
        'found': len(results) > 0,
        'matches': [{
            'id': r.id,
            'email': r.email,
            'domain': r.domain,
            'discovered_at': r.discovered_at.isoformat()
        } for r in results]
    })


@threat_bp.route('/attribution/enrich', methods=['POST'])
@jwt_or_api_required
def enrich_actor():
    """Запускает SOCMINT fan-out и обогащает граф атрибуции по alias."""
    payload = request.get_json(silent=True) or {}
    alias = (payload.get('alias') or '').strip()
    if not alias:
        return jsonify({'error': 'alias is required'}), 400

    email = (payload.get('email') or '').strip()

    async def _enrich_and_get():
        if email:
            await graph_db.add_relation(alias, "THREAT_ACTOR", email, "EMAIL", "HAS_EMAIL", weight=0.9)
        result = await graph_db.get_object_relations(alias)
        return {"alias": alias, "connections": result.get("connections", [])}

    try:
        profile = asyncio.run(_enrich_and_get())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            profile = loop.run_until_complete(_enrich_and_get())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return jsonify(profile)


@threat_bp.route('/attribution/profile/<alias>', methods=['GET'])
@jwt_or_api_required
def get_actor_profile(alias):
    """Возвращает текущий профиль актора из графа атрибуции."""
    try:
        result = asyncio.run(graph_db.get_object_relations(alias))
        profile = {"alias": alias, "connections": result.get("connections", [])}
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(graph_db.get_object_relations(alias))
            profile = {"alias": alias, "connections": result.get("connections", [])}
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return jsonify(profile)



@threat_bp.route('/assets/risk/enrich', methods=['POST'])
@jwt_or_api_required
def enrich_assets_risk():
    """Запускает обогащение графа рисков для owned-активов (домены компании)."""
    payload = request.get_json(silent=True) or {}
    owned_domains = payload.get('owned_domains') or []

    if not isinstance(owned_domains, list) or not all(isinstance(d, str) and d.strip() for d in owned_domains):
        return jsonify({'error': 'owned_domains must be a non-empty list of domains'}), 400

    normalized = [d.strip().lower() for d in owned_domains]

    try:
        profile = asyncio.run(enrich_asset_risk(normalized))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            profile = loop.run_until_complete(enrich_asset_risk(normalized))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return jsonify(profile)
