# Then generate the Python gRPC code by running:
# python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hello.proto

# server.py
import grpc
from concurrent import futures
import hello_pb2
import hello_pb2_grpc
import json

class Greeter(hello_pb2_grpc.GreeterServicer):
    def SayHello(self, request, context):
        repo_data = json.loads(request.data)
        # Calcola le metriche (esempio)
        result = {
            "num_contributors": len(repo_data.get("contributors", [])),
            "repo_name": repo_data.get("name", "")
        }
        return hello_pb2.HelloReply(message=json.dumps(result))

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    hello_pb2_grpc.add_GreeterServicer_to_server(Greeter(), server)
    server.add_insecure_port('[::]:50051')
    print("gRPC Python server in ascolto sulla porta 50051")  # Conferma avvio
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()