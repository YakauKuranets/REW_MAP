# -*- coding: utf-8 -*-
"""
Периодические задачи для анализа утечек.
"""

from celery import shared_task
from app.threat_intel.leak_analyzer import LeakAnalyzer
from app.darknet.models import DarknetPost
from app.extensions import db
import logging

logger = logging.getLogger(__name__)


@shared_task
def analyze_recent_posts():
    """
    Анализирует новые посты за последние 24 часа.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    posts = DarknetPost.query.filter(
        DarknetPost.discovered_at >= cutoff,
        DarknetPost.analyzed == False
    ).limit(200).all()

    analyzer = LeakAnalyzer()
    results = analyzer.analyze_batch(posts)

    for post in posts:
        post.analyzed = True
    db.session.commit()

    logger.info(f"Analyzed {len(results)} new posts")
    return len(results)


@shared_task
def check_critical_matches():
    """
    Проверяет критические совпадения и отправляет уведомления.
    """
    from app.threat_intel.target_matcher import TargetMatcher
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=1)
    posts = DarknetPost.query.filter(
        DarknetPost.discovered_at >= cutoff
    ).all()

    matcher = TargetMatcher()
    critical_matches = []

    for post in posts:
        matches = matcher.find_matches(post)
        if matches:
            critical_matches.append({
                'post_id': post.id,
                'url': post.url,
                'matches': matches
            })

    if critical_matches:
        # Отправка уведомлений через Telegram/email
        logger.warning(f"Found {len(critical_matches)} critical matches")
        # TODO: интеграция с системой оповещения

    return len(critical_matches)
