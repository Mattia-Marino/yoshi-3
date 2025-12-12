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

# Add generated directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))

import processor_pb2
import processor_pb2_grpc
from formality_calculator import FormalityCalculator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        Process repository data and compute formality metric.
        
        Args:
            request: ProcessRequest containing repository data
            context: gRPC context
            
        Returns:
            ProcessResponse: Formality score
        """
        try:
            logger.info("Process request received")
            
            # Extract repository data from proto message
            repo = request.repository
            logger.info(f"Repository: {repo.owner}/{repo.repo}")
            
            # Convert proto message to dictionary for formality calculator
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
                }
            }
            
            # Compute formality metric
            formality_score = FormalityCalculator.compute(repo_data)
            logger.info(f"Computed formality score: {formality_score}")
            
            # Return direct response
            return processor_pb2.ProcessResponse(
                formality=formality_score
            )
            
        except Exception as e:
            logger.error(f"Processing error: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Processing error: {str(e)}")
            return processor_pb2.ProcessResponse(formality=0.0)


def serve():
    """
    Start the gRPC server and listen for incoming requests.
    """
    logger.info("Starting gRPC Processing Server...")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    processor_pb2_grpc.add_ProcessorServiceServicer_to_server(
        ProcessorServicer(), server
    )
    server.add_insecure_port('[::]:50051')
    logger.info("gRPC Processing Server listening on port 50051")
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    serve()