class FormalityCalculator:
    WEIGHTS = {
        "HasCoC": 1.8,
        "HasReadMe": 0.2,
        "HasDescription": 0.2,
        "HasContributingGuidelines": 1.8,
        "HasLicense": 0.5,
        "HasSecurityPolicy": 0.7,
        "HasIssuesTemplate": 1.8,
        "HasPullRequestTemplate": 1.5,
        "HasWikiPage": 0.5,
        "HasMilestones": 1.0
    }

    @staticmethod
    def compute(repo_json):
        score = 0
        for key, weight in FormalityCalculator.WEIGHTS.items():
            score += int(bool(repo_json.get(key, False))) * weight
        # Normalize by sum of weights
        max_score = sum(FormalityCalculator.WEIGHTS.values())
        return score / max_score if max_score else 0