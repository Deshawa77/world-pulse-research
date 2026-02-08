from processing.global_risk import compute_global_risk

def generate_summary():
    """
    Generate a clean executive AI summary with risk level and top topics.
    
    Returns:
        str: Summary like:
            ⚠️ HIGH RISK: Global Risk Score: 72.5/100.
            Top topics influencing sentiment today: earthquake, flooding, inflation.
    """
    try:
        # Compute risk score and top topics safely
        score, topics = compute_global_risk()
    except Exception as e:
        # Fallback if something fails
        score = 0
        topics = ["multiple global factors"]
    
    # Format topics
    topic_text = ", ".join(topics) if topics else "multiple global factors"

    # Determine risk level
    if score > 70:
        risk_label = "⚠️ HIGH RISK"
    elif score > 40:
        risk_label = "Moderate risk"
    else:
        risk_label = "Low risk"

    # Compose summary
    summary = (
        f"{risk_label}: Global Risk Score: {score:.1f}/100.\n"
        f"Top topics influencing sentiment today: {topic_text}."
    )

    return summary
