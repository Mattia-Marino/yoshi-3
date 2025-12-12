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
            request: ProcessRequest containing repository JSON data
            context: gRPC context
            
        Returns:
            ProcessResponse: JSON string with computed formality metric
        """
        try:
            logger.info("Process request received")
            logger.debug(f"Request type: {type(request)}")
            logger.debug(f"Request fields: {request.DESCRIPTOR.fields}")
            
            # Log raw input for debugging
            raw_json = request.repository_json
            logger.info(f"Received JSON length: {len(raw_json)} characters")
            logger.debug(f"First 200 chars: {raw_json[:200]}")
            
            if not raw_json or raw_json.strip() == "":
                logger.error("Received empty JSON string")
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Empty JSON input received")
                return processor_pb2.ProcessResponse(result_json="{}")
            
            # Parse input JSON
            repo_data = json.loads(raw_json)
            logger.info(f"Successfully parsed JSON with keys: {list(repo_data.keys())}")
            
            # Compute formality metric
            formality_score = FormalityCalculator.compute(repo_data)
            logger.info(f"Computed formality score: {formality_score}")
            
            # Prepare result JSON
            result = {
                "formality": formality_score
            }
            
            result_json = json.dumps(result)
            logger.info(f"Returning result: {result_json}")
            
            return processor_pb2.ProcessResponse(
                result_json=result_json
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            logger.error(f"Problematic input: {request.repository_json[:500]}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(f"Invalid JSON input: {str(e)}")
            return processor_pb2.ProcessResponse(result_json="{}")
            
        except Exception as e:
            logger.error(f"Processing error: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Processing error: {str(e)}")
            return processor_pb2.ProcessResponse(result_json="{}")


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