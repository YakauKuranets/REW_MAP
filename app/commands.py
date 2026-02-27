"""Flask CLI commands."""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.auth.models import User


@click.command('create-admin')
@click.option('--username', prompt=True)
@click.option('--email', prompt=True)
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def create_admin(username: str, email: str, password: str) -> None:
    """Создаёт пользователя с правами администратора."""
    existing = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing:
        raise click.ClickException('User with the same username/email already exists')

    user = User(username=username, email=email, role='admin', is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f'Admin {username} created.')


@click.command("update-wordlists")
@with_appcontext
def update_wordlists_command() -> None:
    """Запускает обновление словарей."""
    from app.tasks.wordlist_updater import update_wordlists

    update_wordlists.delay()
    click.echo("Wordlist update task enqueued.")
