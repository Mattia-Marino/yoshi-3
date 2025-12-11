import requests
import grpc
import hello_pb2
import hello_pb2_grpc
import json

def get_repo_data(owner, repo):
    url = "http://localhost:6001/extract"
    payload = {"owner": owner, "repo": repo}
    response = requests.post(url, json=payload)
    return response.json()

def send_to_grpc_server(repo_json):
    channel = grpc.insecure_channel('localhost:50051')
    stub = hello_pb2_grpc.GreeterStub(channel)
    # Invia i dati come stringa JSON
    grpc_response = stub.SayHello(hello_pb2.HelloRequest(data=json.dumps(repo_json)))
    print("Risposta dal server Python:", grpc_response.message)

if __name__ == "__main__":
    owner = "tensorflow"
    repo = "tensorflow"
    repo_json = get_repo_data(owner, repo)
    send_to_grpc_server(repo_json)