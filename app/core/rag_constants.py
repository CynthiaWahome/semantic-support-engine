"""Default values for the reusable RAG safeguards."""

DEFAULT_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_RATE_LIMIT_PER_HOUR = 10
DEFAULT_RATE_WINDOW_SECONDS = 60 * 60

# These reproduce the original policy. Consumers should inject their own policy
# when the assistant is used outside the original cohort workflow.
DEFAULT_BLOCKED_TOPICS = (
    "promotion criteria",
    "stage promotion",
    "intern record",
    "personal score",
)
