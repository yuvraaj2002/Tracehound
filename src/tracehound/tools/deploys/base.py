"""The base class every deploy backend adapter extends."""

from tracehound.schemas.deploys import Deploy
from tracehound.tools.source import Source


class DeploySource(Source[Deploy]):
    """Fetches deployments from one backend and returns them as canonical ``Deploy``s.

    ``fetch`` returns deploys to ``services`` with ``start <= deployed_at <= end``, oldest first.
    """
