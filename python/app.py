# Then generate the Python gRPC code by running:
# python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hello.proto

# server.py
import grpc
from concurrent import futures
import time

# Import the generated classes
import hello_pb2
import hello_pb2_grpc


class GreeterServicer(hello_pb2_grpc.GreeterServicer):
    """Implementation of the Greeter service."""
    
    def SayHello(self, request, context):
        """Handles the SayHello RPC call."""
        name = request.name if request.name else "World"
        message = f"Hello {name}!"
        print(f"Received request from: {name}")
        return hello_pb2.HelloReply(message=message)


def serve():
    """Start the gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    hello_pb2_grpc.add_GreeterServicer_to_server(GreeterServicer(), server)
    
    port = "50051"
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    
    print(f"Server started on port {port}")
    print("Waiting for requests...")
    
    try:
        while True:
            time.sleep(86400)  # Keep server running
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop(0)


if __name__ == "__main__":
    serve()