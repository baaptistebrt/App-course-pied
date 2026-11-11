"""
Envoi automatique du code d'accès par e-mail (SMTP, sans service payant).

Configuration dans les Secrets Streamlit (ou .streamlit/secrets.toml) :

    [email]
    user = "ton.adresse@gmail.com"           # compte qui envoie
    password = "abcd efgh ijkl mnop"         # mot de passe d'application Gmail (16 lettres)
    sender_name = "Ton coach"                # facultatif : nom affiché
    app_url = "https://ton-app.streamlit.app" # facultatif : lien mis dans l'e-mail
    # facultatif (Gmail par défaut) : host = "smtp.gmail.com", port = 587 (STARTTLS, testé sur Streamlit Cloud)

Avec Gmail : la validation en deux étapes doit être activée, puis un « mot de passe d'application »
créé sur https://myaccount.google.com/apppasswords. Le mot de passe habituel ne fonctionne pas.
"""

from __future__ import annotations

import html
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from .config import DISTANCES


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    user: str
    password: str
    sender_name: str = "Ton coach"
    app_url: str = ""
    security: str = "ssl"      # « ssl » (465), « starttls » (587) ou « none » (tests)


def load_email_config() -> EmailConfig | None:
    """Configuration e-mail depuis les Secrets ou les variables d'environnement, sinon None."""
    conf: dict = {}
    try:
        import streamlit as st

        conf = dict(st.secrets.get("email", {}))
    except Exception:  # pas de secrets.toml
        conf = {}
    get = lambda k, env=None, default="": str(conf.get(k) or os.environ.get(env or f"PLAN_EMAIL_{k.upper()}", default))  # noqa: E731
    user, password = get("user"), get("password")
    if not (user and password):
        return None
    port = int(get("port", default="587") or 587)
    security = get("security", default="") or ("ssl" if port == 465 else "starttls" if port == 587 else "none")
    return EmailConfig(host=get("host", default="smtp.gmail.com"), port=port, user=user, password=password,
                       sender_name=get("sender_name", default="Ton coach"), app_url=get("app_url"),
                       security=security)


def build_access_email(student, config: EmailConfig, app_url: str) -> EmailMessage:
    """E-mail (texte + HTML) avec le lien de l'application et le code d'accès."""
    dist = DISTANCES[student.distance].label
    course = getattr(student, "course", "").strip()
    plan_name = f"pour {course}" if course else dist.lower()
    name = student.prenom or ""
    msg = EmailMessage()
    msg["Subject"] = f"Ton plan d'entraînement {plan_name} est prêt"
    msg["From"] = formataddr((config.sender_name, config.user))
    msg["To"] = student.email
    text = (f"Bonjour {name},\n\n" if name else "Bonjour,\n\n") + (
        f"Ton plan d'entraînement {plan_name} t'attend.\n\n"
        f"1. Ouvre l'application : {app_url}\n"
        f"2. Saisis ton code d'accès : {student.code}\n\n"
        "Tu y trouveras ta prochaine séance, tes allures et ton plan semaine par semaine. Coche chaque "
        "séance réalisée et dis comment tu l'as sentie : ton coach suit tes ressentis.\n\n"
        "Garde ce code pour toi : il donne accès à ton plan.\n\n"
        f"Bonne préparation !\n{config.sender_name}\n")
    e = html.escape
    msg.set_content(text)
    msg.add_alternative(f"""\
<div style="font-family:Arial,Helvetica,sans-serif;color:#14233A;max-width:520px">
  <p>{'Bonjour ' + e(name) + ',' if name else 'Bonjour,'}</p>
  <p>Ton plan d'entraînement <b>{e(plan_name)}</b> t'attend.</p>
  <p style="margin:22px 0">
    <a href="{e(app_url)}" style="background:#1B4F8C;color:#fff;text-decoration:none;padding:12px 20px;
       border-radius:8px;font-weight:bold">Ouvrir mon plan</a>
  </p>
  <p>Ton code d'accès :</p>
  <p style="font-size:26px;font-weight:bold;letter-spacing:2px;background:#FFC629;display:inline-block;
     padding:6px 14px;border-radius:6px">{e(student.code)}</p>
  <p>Tu y trouveras ta prochaine séance, tes allures et ton plan semaine par semaine. Coche chaque séance
     réalisée et dis comment tu l'as sentie : ton coach suit tes ressentis.</p>
  <p style="color:#5B6B80;font-size:13px">Garde ce code pour toi : il donne accès à ton plan.<br>
     Lien : <a href="{e(app_url)}">{e(app_url)}</a></p>
  <p>Bonne préparation !<br>{e(config.sender_name)}</p>
</div>""", subtype="html")
    return msg


def send_message(msg: EmailMessage, config: EmailConfig, timeout: float = 20) -> None:
    if config.security == "ssl":
        with smtplib.SMTP_SSL(config.host, config.port, context=ssl.create_default_context(), timeout=timeout) as s:
            s.login(config.user, config.password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(config.host, config.port, timeout=timeout) as s:
            if config.security == "starttls":
                s.starttls(context=ssl.create_default_context())
            if config.security != "none" or config.password:
                try:
                    s.login(config.user, config.password)
                except smtplib.SMTPNotSupportedError:
                    pass
            s.send_message(msg)


def send_access_email(student, config: EmailConfig | None, app_url: str) -> tuple[bool, str]:
    """Envoie le code à l'élève. Renvoie (succès, message lisible pour le coach)."""
    if config is None:
        return False, "Envoi d'e-mails non configuré (voir l'onglet Réglages) : transmets le code toi-même."
    url = config.app_url or app_url
    if not url:
        return False, "Adresse de l'application inconnue : renseigne app_url dans les Secrets [email]."
    try:
        send_message(build_access_email(student, config, url), config)
    except smtplib.SMTPAuthenticationError:
        return False, ("Connexion refusée par le serveur e-mail : vérifie l'adresse et le mot de passe "
                       "d'application dans les Secrets.")
    except Exception as exc:  # réseau, adresse refusée…
        return False, f"L'e-mail n'a pas pu partir ({exc})."
    return True, f"Code envoyé par e-mail à {student.email}."


def send_test_email(config: EmailConfig, to: str) -> tuple[bool, str]:
    msg = EmailMessage()
    msg["Subject"] = "Test d'envoi : application de plans d'entraînement"
    msg["From"] = formataddr((config.sender_name, config.user))
    msg["To"] = to
    msg.set_content("Si tu lis ce message, l'envoi automatique des codes d'accès fonctionne.")
    try:
        send_message(msg, config)
    except Exception as exc:
        return False, f"Échec de l'envoi : {exc}"
    return True, f"E-mail de test envoyé à {to}."
