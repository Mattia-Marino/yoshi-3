from datetime import datetime

class LongevityCalculator:
    @staticmethod
    def compute(commit_history, yearly_threshold=10):
        """
        :param commit_history: dict mapping year (int) to number of commits (int)
        :param yearly_threshold: int, minimum commits per year to count as 'active'
        :return: float, longevity score
        """
        years = sorted(commit_history.keys())
        if not years:
            return 0.0

        # Yearly Continuity
        total_years = len(years)
        active_years = sum(1 for y in years if commit_history[y] >= yearly_threshold)
        yearly_continuity = active_years / total_years if total_years else 0

        # Stability
        # Assume commit_history contains all years in the repo's life
        # Find the longest streak of consecutive years with < yearly_threshold commits
        longest_nocommit_streak = 0
        current_streak = 0
        for y in years:
            if commit_history[y] < yearly_threshold:
                current_streak += 1
                longest_nocommit_streak = max(longest_nocommit_streak, current_streak)
            else:
                current_streak = 0
        # Convert years to days (approximate)
        longest_nocommit_days = longest_nocommit_streak * 365
        stability = 1 - (longest_nocommit_days / (total_years * 365)) if total_years else 0

        # Weighted average
        longevity_score = 0.5 * yearly_continuity + 0.5 * stability
        return longevity_score