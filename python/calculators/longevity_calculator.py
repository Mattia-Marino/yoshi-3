"""
Longevity Calculator

Computes longevity score based on four dimensions:
- Efficiency (PR Acceptance Rate)
- Resilience (Development Distribution via Gini Coefficient)
- Loyalty (Contributor Retention)
- Consistency (Technical Pulse)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class LongevityCalculator:
    """
    Calculator for computing longevity based on PR acceptance, development distribution,
    contributor retention, and technical pulse.
    """
    
    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse ISO 8601 date string to datetime object."""
        if not date_str or date_str == "null":
            return None
        try:
            # Handle timezone format
            if date_str.endswith('Z'):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return datetime.fromisoformat(date_str)
        except:
            return None
    
    @staticmethod
    def _compute_pr_acceptance_rate(pull_requests: List[Dict]) -> float:
        """
        Compute PR Acceptance Rate: A_pr = Merged PRs / Closed PRs
        
        Args:
            pull_requests: List of pull request dicts with 'status' and 'merged_at' fields
            
        Returns:
            float: PR acceptance rate (0.0 to 1.0)
        """
        if not pull_requests:
            logger.debug("  No pull requests found")
            return 0.0
        
        # Count merged and closed PRs
        merged_count = 0
        closed_count = 0
        
        for pr in pull_requests:
            status = pr.get("status", "").lower()
            
            # Count as closed if status is 'closed' or 'merged'
            if status == "merged":
                merged_count += 1
                closed_count += 1
            elif status == "closed":
                closed_count += 1
        
        logger.debug(f"  Total PRs: {len(pull_requests)}")
        logger.debug(f"  Merged PRs: {merged_count}")
        logger.debug(f"  Closed PRs (including merged): {closed_count}")
        logger.debug(f"  Open PRs: {len(pull_requests) - closed_count}")
        
        if closed_count == 0:
            logger.debug("  No closed PRs found, returning 0.0")
            return 0.0
        
        acceptance_rate = merged_count / closed_count
        logger.debug(f"  PR Acceptance Rate (A_pr): {acceptance_rate:.4f} ({merged_count}/{closed_count})")
        
        return acceptance_rate
    
    @staticmethod
    def _compute_development_distribution(contributor_stats: List[Dict]) -> float:
        """
        Compute Development Distribution via Gini Coefficient: D_dist = 1 - G
        
        The Gini coefficient measures inequality in commit distribution.
        G = 0 means perfect equality (everyone contributes equally)
        G = 1 means perfect inequality (one person does everything)
        
        Args:
            contributor_stats: List of contributor stat dicts with 'author' and 'total' fields
            
        Returns:
            float: Development distribution score (0.0 to 1.0), higher is better
        """
        if not contributor_stats:
            logger.debug("  No contributor stats found")
            return 0.0
        
        # Extract commit counts from contributor stats
        counts = [stat.get("total", 0) for stat in contributor_stats if stat.get("total", 0) > 0]
        counts.sort()
        
        n = len(counts)
        total_commits = sum(counts)
        n = len(counts)
        total_commits = sum(counts)
        
        logger.debug(f"  Total commits: {total_commits}")
        logger.debug(f"  Unique contributors: {n}")
        logger.debug(f"  Commits per contributor: min={min(counts)}, max={max(counts)}, mean={total_commits/n:.2f}")
        
        if n == 0:
            logger.debug("  No contributors found, returning 0.0")
            return 0.0
        
        if n == 1:
            logger.debug("  Only one contributor, perfect inequality, returning 0.0")
            return 0.0
        
        # Compute Gini coefficient
        # G = sum((2i - n - 1) * x_i) / (n * sum(x_i))
        numerator = sum((2 * i - n - 1) * x for i, x in enumerate(counts, start=1))
        denominator = n * sum(counts)
        
        gini = numerator / denominator
        
        # D_dist = 1 - G (higher is better)
        d_dist = 1 - gini
        
        logger.debug(f"  Gini Coefficient: {gini:.4f}")
        logger.debug(f"  Development Distribution (D_dist): {d_dist:.4f} (1 - {gini:.4f})")
        
        return d_dist
    
    @staticmethod
    def _compute_contributor_retention(contributor_stats: List[Dict]) -> float:
        """
        Compute Contributor Retention: C_ret = Contributors with tenure > 365 days / Total contributors
        
        Tenure is calculated as the time between first and last commit for each contributor.
        
        Args:
            contributor_stats: List of contributor stat dicts with 'first_commit' and 'last_commit' fields
            
        Returns:
            float: Contributor retention rate (0.0 to 1.0)
        """
        if not contributor_stats:
            logger.debug("  No contributor stats found")
            return 0.0
        
        # Calculate tenure for each contributor
        long_term_contributors = 0
        total_contributors = 0
        
        for stat in contributor_stats:
            first_commit_str = stat.get("first_commit")
            last_commit_str = stat.get("last_commit")
            
            if not first_commit_str or not last_commit_str:
                continue
            
            first_commit = LongevityCalculator._parse_date(first_commit_str)
            last_commit = LongevityCalculator._parse_date(last_commit_str)
            
            if not first_commit or not last_commit:
                continue
            
            total_contributors += 1
            tenure_days = (last_commit - first_commit).days
            
            if tenure_days > 365:
                long_term_contributors += 1
        
        logger.debug(f"  Total contributors: {total_contributors}")
        logger.debug(f"  Contributors with tenure > 365 days: {long_term_contributors}")
        
        if total_contributors == 0:
            logger.debug("  No contributors found, returning 0.0")
            return 0.0
        
        retention_rate = long_term_contributors / total_contributors
        logger.debug(f"  Contributor Retention (C_ret): {retention_rate:.4f} ({long_term_contributors}/{total_contributors})")
        
        return retention_rate
    
    @staticmethod
    def _compute_technical_pulse(contributor_stats: List[Dict]) -> float:
        """
        Compute Technical Pulse: P_tech = Active weeks in last year / 52
        
        Counts how many weeks in the previous year had at least 1 commit.
        
        Args:
            contributor_stats: List of contributor stat dicts with 'weeks' field
            
        Returns:
            float: Technical pulse score (0.0 to 1.0)
        """
        if not contributor_stats:
            logger.debug("  No contributor stats found")
            return 0.0
        
        # Find the most recent commit date from all contributors
        all_last_commits = []
        for stat in contributor_stats:
            last_commit_str = stat.get("last_commit")
            if last_commit_str:
                last_commit_date = LongevityCalculator._parse_date(last_commit_str)
                if last_commit_date:
                    all_last_commits.append(last_commit_date)
        
        if not all_last_commits:
            logger.debug("  No valid commit dates found")
            return 0.0
        
        # Use the most recent commit date as the reference point
        reference_date = max(all_last_commits)
        one_year_ago = reference_date - timedelta(days=365)
        one_year_ago_timestamp = int(one_year_ago.timestamp())
        
        logger.debug(f"  Reference date (most recent commit): {reference_date.date()}")
        logger.debug(f"  One year ago: {one_year_ago.date()}")
        
        # Track which weeks had commits in the last year
        active_weeks = set()
        commits_in_period = 0
        
        for stat in contributor_stats:
            weeks = stat.get("weeks")
            if not weeks:
                continue
            
            for week in weeks:
                week_timestamp = week.get("week", 0)
                week_commits = week.get("commits", 0)
                
                # Check if this week is within the last year
                if week_timestamp >= one_year_ago_timestamp and week_commits > 0:
                    # Convert timestamp to datetime for week calculation
                    week_date = datetime.fromtimestamp(week_timestamp)
                    iso_year, iso_week, _ = week_date.isocalendar()
                    week_key = (iso_year, iso_week)
                    active_weeks.add(week_key)
                    commits_in_period += week_commits
        
        active_week_count = len(active_weeks)
        
        logger.debug(f"  Commits in last year: {commits_in_period}")
        logger.debug(f"  Active weeks in last year: {active_week_count}/52")
        
        technical_pulse = active_week_count / 52.0
        logger.debug(f"  Technical Pulse (P_tech): {technical_pulse:.4f} ({active_week_count}/52)")
        
        return technical_pulse
    
    @classmethod
    def compute(cls, repo_data: Dict) -> float:
        """
        Compute longevity score from repository data.
        
        Longevity is computed as:
        L = 0.30*D_dist + 0.30*C_ret + 0.25*A_pr + 0.15*P_tech
        
        Where:
        - D_dist: Development Distribution (1 - Gini coefficient)
        - C_ret: Contributor Retention (contributors with tenure > 1 year)
        - A_pr: PR Acceptance Rate (merged PRs / closed PRs)
        - P_tech: Technical Pulse (active weeks / 52)
        
        Args:
            repo_data: Dictionary containing repository information with commits and PRs
            
        Returns:
            float: Longevity score (0.0 to 1.0)
        """
        # Extract repository object if nested
        if "repository" in repo_data:
            repo = repo_data["repository"]
        else:
            repo = repo_data
        
        logger.debug("=" * 60)
        logger.debug("Starting longevity computation")
        logger.debug("=" * 60)
        
        # Extract data
        contributor_stats = repo.get("contributor_stats", [])
        pull_requests = repo.get("pull_requests", [])
        
        logger.debug(f"Input data: {len(contributor_stats)} contributors, {len(pull_requests)} pull requests")
        
        # Compute each dimension
        logger.debug("\n1. Computing PR Acceptance Rate (A_pr)...")
        a_pr = cls._compute_pr_acceptance_rate(pull_requests)
        
        logger.debug("\n2. Computing Development Distribution (D_dist)...")
        d_dist = cls._compute_development_distribution(contributor_stats)
        
        logger.debug("\n3. Computing Contributor Retention (C_ret)...")
        c_ret = cls._compute_contributor_retention(contributor_stats)
        
        logger.debug("\n4. Computing Technical Pulse (P_tech)...")
        p_tech = cls._compute_technical_pulse(contributor_stats)
        
        # Calculate final longevity score
        longevity = (0.30 * d_dist) + (0.30 * c_ret) + (0.25 * a_pr) + (0.15 * p_tech)
        
        logger.debug("\n" + "=" * 60)
        logger.debug("Longevity Score Breakdown:")
        logger.debug(f"  D_dist (Development Distribution): {d_dist:.4f} × 0.30 = {0.30 * d_dist:.4f}")
        logger.debug(f"  C_ret  (Contributor Retention):    {c_ret:.4f} × 0.30 = {0.30 * c_ret:.4f}")
        logger.debug(f"  A_pr   (PR Acceptance Rate):       {a_pr:.4f} × 0.25 = {0.25 * a_pr:.4f}")
        logger.debug(f"  P_tech (Technical Pulse):          {p_tech:.4f} × 0.15 = {0.15 * p_tech:.4f}")
        logger.debug(f"  ────────────────────────────────────────────────")
        logger.debug(f"  Final Longevity Score:             {longevity:.4f}")
        logger.debug("=" * 60)
        
        return longevity
