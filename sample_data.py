from __future__ import annotations
from datetime import datetime, timedelta


def sample_mentions() -> list[dict]:
    now = datetime.now()
    return [
        {
            "date": (now - timedelta(days=1)).isoformat(timespec="seconds"),
            "source": "Sample news",
            "source_type": "news",
            "title": "Residents raise concerns about tree clearing and slope stability near proposed line",
            "text": "Residents are worried about trees, erosion, and slope stability related to the proposed transmission project.",
            "url": "https://example.com/news/tree-clearing",
        },
        {
            "date": (now - timedelta(days=2)).isoformat(timespec="seconds"),
            "source": "Sample reddit",
            "source_type": "reddit",
            "title": "Does anyone know if the new powerline affects property values?",
            "text": "People are asking about property values, EMF, and whether consultation has been transparent.",
            "url": "https://example.com/reddit/property-values",
        },
        {
            "date": (now - timedelta(days=5)).isoformat(timespec="seconds"),
            "source": "Sample municipal",
            "source_type": "municipal",
            "title": "Council agenda includes delegation on proposed infrastructure corridor",
            "text": "A delegation is expected to speak about farmland, traffic, and construction disruption.",
            "url": "https://example.com/council/agenda",
        },
        {
            "date": (now - timedelta(days=9)).isoformat(timespec="seconds"),
            "source": "Sample blog",
            "source_type": "web",
            "title": "Project team shares updated routing study and environmental commitments",
            "text": "The project update describes mitigation, consultation, and efforts to avoid wetlands where feasible.",
            "url": "https://example.com/project/update",
        },
    ]
