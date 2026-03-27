"""
Cohesion Calculator

Computes cohesion as directed-graph completeness among repository contributors.
Each contributor is a node. A directed edge i -> j exists when contributor i
follows contributor j within the same repository community.

Using contributor-level counts already extracted by the Go service:
- following = out-degree of the contributor node
- followers = in-degree of the contributor node

Cohesion is graph completeness (density) in [0, 1]:
cohesion = E / (N * (N - 1))
where E is the estimated number of directed edges and N is the number of
contributors considered.
"""

from typing import Dict, List, Any


class CohesionCalculator:
    """Calculator for computing cohesion from internal follow relationships."""

    @staticmethod
    def _to_int(value: Any) -> int:
        """Convert a value to int safely, defaulting to 0 for invalid values."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def compute(cls, repo_data: Dict) -> float:
        """
        Compute cohesion as directed graph completeness among contributors.

        Args:
            repo_data: Dictionary containing repository information.

        Returns:
            float: Cohesion score in [0, 1].
        """
        repo = repo_data.get("repository", repo_data)
        contributors: List[Dict] = repo.get("contributors", [])

        n = len(contributors)
        if n < 2:
            return 0.0

        max_degree = n - 1
        total_following = 0
        total_followers = 0

        for contributor in contributors:
            following = cls._to_int(contributor.get("following", 0))
            followers = cls._to_int(contributor.get("followers", 0))

            following = max(0, min(following, max_degree))
            followers = max(0, min(followers, max_degree))

            total_following += following
            total_followers += followers

        # In a directed graph, sum(out-degree) == sum(in-degree) == E.
        # Averaging makes the estimate robust to partial retrieval mismatches.
        estimated_edges = (total_following + total_followers) / 2.0
        possible_edges = n * (n - 1)

        if possible_edges <= 0:
            return 0.0

        cohesion = estimated_edges / possible_edges
        return max(0.0, min(1.0, cohesion))
