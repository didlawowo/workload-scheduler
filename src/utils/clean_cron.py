def clean_cron_expression(expression):
    """Clean and normalize a CRON expression"""
    if not expression:
        return "* * * * *"

    cleaned = ' '.join(expression.split())

    parts = cleaned.split(' ')

    while len(parts) < 5:
        parts.append('*')

    if len(parts) > 5:
        parts = parts[:5]

    return ' '.join(parts)