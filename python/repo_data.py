from formality_calculator import FormalityCalculator
from longevity_calculator import LongevityCalculator


class RepoData:
    def __init__(self, repo_json):
        """
        Initialize with a JSON object containing repository data.
        :param repo_json: dict, JSON data retrieved from Go
        """
        self.data = repo_json

    def get_owner(self):
        return self.data.get("owner")

    def get_repo(self):
        return self.data.get("repo")

    def get_field(self, field_name):
        """
        Generic getter for any field in the JSON.
        :param field_name: str
        :return: value or None
        """
        return self.data.get(field_name)

    def get_formality_score(self):
        return FormalityCalculator.compute(self.data)

    def get_longevity_score(self, yearly_threshold=10):
        commit_history = self.data.get("commit_history", {})
        return LongevityCalculator.compute(commit_history, yearly_threshold)

    def __repr__(self):
        return f"RepoData({self.data})"