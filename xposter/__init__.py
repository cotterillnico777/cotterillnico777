"""xposter – Posts für einen X-Account vorbereiten, freigeben und über die offizielle API veröffentlichen.

Grundsätze:
  - Nichts wird ohne ausdrückliche Freigabe (approve) gepostet.
  - Schlüssel nur aus der Umgebung / .env, nie im Code, nie im Log.
  - Inhaltsprüfung blockiert Kursversprechen und Contract-Adressen (kein Shilling).
  - Tageslimit und Mindestabstand zwischen Posts.
"""

__version__ = "0.1.0"
