from typing import Optional
from loguru import logger

def clean_cron_expression(expression: Optional[str] = None) -> str:
    """
    Nettoie et normalise une expression CRON.

    Cette fonction s'assure que l'expression CRON a exactement 5 parties
    (minute, heure, jour du mois, mois, jour de la semaine).
    """
    logger.debug(f"Nettoyage de l'expression CRON: '{expression}'")

    if not expression:
        logger.debug("Expression vide ou None, utilisation de l'expression par défaut")
        return "* * * * *"

    cleaned = ' '.join(expression.split())
    logger.debug(f"Expression après normalisation des espaces: '{cleaned}'")
    parts = cleaned.split(' ')

    if len(parts) < 5:
        logger.debug(f"Expression incomplète ({len(parts)}/5 parties), ajout des parties manquantes")
        while len(parts) < 5:
            parts.append('*')
    if len(parts) > 5:
        logger.debug(f"Expression trop longue ({len(parts)}/5 parties), suppression des parties excédentaires")
        parts = parts[:5]

    result = ' '.join(parts)
    logger.debug(f"Expression CRON nettoyée: '{result}'")
    return result