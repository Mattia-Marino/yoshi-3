"""
gRPC Processing Server for GitHub Repository Metrics

Generate the Python gRPC code by running:
./generate.sh
"""

import grpc
from concurrent import futures
import sys
import os
import json
import logging
import argparse

# Add generated directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))

import processor_pb2
import processor_pb2_grpc
from calculators import FormalityCalculator, GeodispersionCalculator, LongevityCalculator

# Logger will be configured in main
logger = logging.getLogger(__name__)


class ProcessorServicer(processor_pb2_grpc.ProcessorServiceServicer):
    """
    gRPC service implementation for processing GitHub repository data.
    """
    
    def Health(self, request, context):
        """
        Health check endpoint.
        
        Returns:
            HealthResponse: Status and message indicating service health
        """
        logger.info("Health check requested")
        return processor_pb2.HealthResponse(
            status="healthy",
            message="Processing service is running"
        )
    
    def Process(self, request, context):
        """
        Process repository data and compute metrics.
        
        Args:
            request: ProcessRequest containing repository data
            context: gRPC context
            
        Returns:
            ProcessResponse: Formality and geodispersion scores
        """
        try:
            logger.info("Process request received")
            
            # Extract repository data from proto message
            repo = request.repository
            logger.info(f"Repository: {repo.owner}/{repo.repo}")
            
            # Convert contributors from proto to dict list
            contributors_data = []
            for contributor in repo.contributors:
                contributors_data.append({
                    "login": contributor.login,
                    "id": contributor.id,
                    "node_id": contributor.node_id,
                    "avatar_url": contributor.avatar_url,
                    "html_url": contributor.html_url,
                    "type": contributor.type,
                    "name": contributor.name,
                    "company": contributor.company,
                    "blog": contributor.blog,
                    "location": contributor.location,
                    "email": contributor.email,
                    "bio": contributor.bio,
                    "created_at": contributor.created_at,
                    "updated_at": contributor.updated_at,
                })
            
            # Convert contributor_stats from proto to dict list
            contributor_stats_data = []
            for stat in repo.contributor_stats:
                # Convert weeks data
                weeks_data = []
                for week in stat.weeks:
                    weeks_data.append({
                        "week": week.week,
                        "additions": week.additions,
                        "deletions": week.deletions,
                        "commits": week.commits,
                    })
                
                contributor_stats_data.append({
                    "author": stat.author,
                    "total": stat.total,
                    "weeks": weeks_data,
                    "first_commit": stat.first_commit,
                    "last_commit": stat.last_commit,
                })
            
            # Convert pull requests from proto to dict list
            pull_requests_data = []
            for pr in repo.pull_requests:
                pull_requests_data.append({
                    "number": pr.number,
                    "status": pr.status,
                    "merged_at": pr.merged_at,
                })
            
            # Convert proto message to dictionary for calculators
            repo_data = {
                "repository": {
                    "owner": repo.owner,
                    "repo": repo.repo,
                    "description": repo.description,
                    "has_code_of_conduct": repo.has_code_of_conduct,
                    "has_readme": repo.has_readme,
                    "has_description": repo.has_description,
                    "has_contributing_guidelines": repo.has_contributing_guidelines,
                    "has_license": repo.has_license,
                    "has_security_policy": repo.has_security_policy,
                    "has_issues_template": repo.has_issues_template,
                    "has_pull_request_template": repo.has_pull_request_template,
                    "has_wiki_page": repo.has_wiki_page,
                    "has_milestones": repo.has_milestones,
                    "contributors": contributors_data,
                    "contributor_stats": contributor_stats_data,
                    "pull_requests": pull_requests_data,
                }
            }
            
            # Compute formality metric
            formality_score = FormalityCalculator.compute(repo_data)
            logger.info(f"Computed formality score: {formality_score}")
            
            # Compute geodispersion metric
            geodispersion_score = GeodispersionCalculator.compute(repo_data)
            logger.info(f"Computed geodispersion score: {geodispersion_score}")
            
            # Compute longevity metric
            longevity_score = LongevityCalculator.compute(repo_data)
            logger.info(f"Computed longevity score: {longevity_score}")
            
            # Return response with all metrics
            return processor_pb2.ProcessResponse(
                formality=formality_score,
                geodispersion=geodispersion_score,
                longevity=longevity_score
            )
            
        except Exception as e:
            logger.error(f"Processing error: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Processing error: {str(e)}")
            return processor_pb2.ProcessResponse(formality=0.0, geodispersion=0.0, longevity=0.0)


def serve(log_level=logging.INFO):
    """
    Start the gRPC server and listen for incoming requests.
    
    Args:
        log_level: Logging level (logging.INFO, logging.DEBUG, etc.)
    """
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Starting gRPC Processing Server...")
    logger.debug(f"Logging level set to: {logging.getLevelName(log_level)}")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    processor_pb2_grpc.add_ProcessorServiceServicer_to_server(
        ProcessorServicer(), server
    )
    server.add_insecure_port('[::]:50051')
    logger.info("gRPC Processing Server listening on port 50051")
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='gRPC Processing Server for GitHub Repository Metrics')
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: INFO)'
    )
    args = parser.parse_args()
    
    # Convert string log level to logging constant
    log_level = getattr(logging, args.log_level.upper())
    
    serve(log_level)