class FormalityCalculator:
    WEIGHTS = {
        "has_code_of_conduct": 1.8,
        "has_readme": 0.2,
        "has_description": 0.2,
        "has_contributing_guidelines": 1.8,
        "has_license": 0.5,
        "has_security_policy": 0.7,
        "has_issues_template": 1.8,
        "has_pull_request_template": 1.5,
        "has_wiki_page": 0.5,
        "has_milestones": 1.0
    }

    @staticmethod
    def compute(repo_data):
        """
        Compute formality score from repository data.
        
        Args:
            repo_data: Dictionary containing repository information
            
        Returns:
            float: Normalized formality score between 0 and 1
        """
        # Extract repository object if nested
        if "repository" in repo_data:
            repo = repo_data["repository"]
        else:
            repo = repo_data
            
        score = 0
        for key, weight in FormalityCalculator.WEIGHTS.items():
            score += int(bool(repo.get(key, False))) * weight
        
        # Normalize by sum of weights (should be 10.0)
        max_score = sum(FormalityCalculator.WEIGHTS.values())
        return score / max_score if max_score else 0