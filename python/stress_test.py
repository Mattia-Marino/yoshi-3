import grpc
import hello_pb2
import hello_pb2_grpc
import threading
import time

def send_request(client_id):
    """Each thread sends a request"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = hello_pb2_grpc.GreeterStub(channel)
    
    print(f"Client {client_id} sending request...")
    response = stub.SayHello(hello_pb2.HelloRequest(name=f'Client-{client_id}'))
    print(f"Client {client_id} received: {response.message}")

def run_stress_test(num_clients):
    """Launch multiple clients simultaneously"""
    threads = []
    
    print(f"Starting {num_clients} concurrent clients...\n")
    start_time = time.time()
    
    # Create and start all threads at once
    for i in range(num_clients):
        thread = threading.Thread(target=send_request, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    end_time = time.time()
    print(f"\n✓ All {num_clients} clients completed in {end_time - start_time:.2f} seconds")

if __name__ == '__main__':
    # Test with different numbers
    print("=== Test 1: 5 concurrent clients ===")
    run_stress_test(5)
    
    print("\n=== Test 2: 10 concurrent clients ===")
    run_stress_test(10)
    
    print("\n=== Test 3: 20 concurrent clients (more than workers!) ===")
    run_stress_test(20)

    print("\n=== Test 4: 30 concurrent clients (more than workers!) ===")
    run_stress_test(30)

    print("\n=== Test 5: 40 concurrent clients (more than workers!) ===")
    run_stress_test(40)

    print("\n=== Test 6: 50 concurrent clients (more than workers!) ===")
    run_stress_test(50)