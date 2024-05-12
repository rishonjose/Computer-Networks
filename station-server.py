import threading
import sys
import socket
from threading import Event

import time
from datetime import datetime
import datetime

 # Global timer and event
response_timer = None
route_discovery_done = threading.Event()

def convert_to_epoch(departure_time_str):
    today = datetime.datetime.now().date()  # get today's date
    departure_time = datetime.datetime.strptime(f"{today} {departure_time_str}", "%Y-%m-%d %H:%M")
    return departure_time.timestamp()  # returns time in seconds since the epoch

def epoch_to_time_only(epoch):
    # Convert epoch time to a datetime object
    dt = datetime.datetime.fromtimestamp(epoch)
    # Format the datetime object to extract only the time in HH:MM format
    return dt.strftime('%H:%M')

def integer_to_epoch_time(time_integer):
    # Extract hours, minutes, and seconds from the integer
    hours = time_integer // 10000
    minutes = (time_integer // 100) % 100
    seconds = time_integer % 100

    # Convert hours, minutes, and seconds to seconds
    total_seconds = hours * 3600 + minutes * 60 + seconds

    # Get current date in struct_time format
    current_date = time.localtime()

    # Convert current date to epoch time
    current_epoch_time = time.mktime(current_date)

    # Calculate epoch time for the given time
    epoch_time = current_epoch_time - (current_date.tm_hour * 3600 + current_date.tm_min * 60 + current_date.tm_sec) + total_seconds

    return epoch_time




# Function to read timetable data from a file
def read_timetable(filename):
    timetable = {}
    with open(filename, 'r') as file:
        for line in file:
            parts = line.strip().split(',')
            if len(parts) < 5 or line[0]=='#':  # Skip any header or malformed lines
                continue
            departure_time, destination = parts[0], parts[4]
            departure_time_int = int(departure_time.replace(':', ''))  # Convert time to integer
            departure_time_int *= 100
            if destination not in timetable:
                timetable[destination] = []
            details = {
                'departure_time': departure_time,
                'bus_train': parts[1],
                'from_stop': parts[2],
                'arrival_time': parts[3]
            }
            if departure_time_int >= leave_time_int:
                timetable[destination].append(details)
    return timetable



def start_http_server(port, timetable, query_port, neighbours, station_name):
    # Start the HTTP server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('localhost', port))
        server_socket.listen(5)
        print(f"HTTP server listening on port {port}...")
        try:
            while True:
                client_socket, addr = server_socket.accept()
                threading.Thread(target=handle_http_request, args=(client_socket, timetable, query_port, neighbours, station_name)).start()
        finally:
            server_socket.close()


def handle_http_request(client_socket, timetable, query_port, neighbours, station_name):
    try:
        request_data = client_socket.recv(1024).decode()
        body_index = request_data.find('\r\n\r\n') + 4
        body = request_data[body_index:]
        headers = request_data[:body_index].split('\r\n')
        content_length = 0
        for header in headers:
            if header.lower().startswith('content-length'):
                content_length = int(header.split(': ')[1])

        while len(body.encode()) < content_length:
            more_data = client_socket.recv(1024).decode()
            body += more_data

        print("Full request body:", body)
        request_lines = request_data.split('\r\n')
        method, path, _ = request_lines[0].split()
        response_content = "Welcome to the Transportation System"
        if method == 'POST' and path == '/':
            form_data = {item.split('=')[0]: item.split('=')[1] for item in body.split('&') if '=' in item}
            destination = form_data.get('destination', "default")
            response_content = process_form_data(destination, timetable, query_port, neighbours, station_name)

        response_data = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><head><title>Response</title></head><body><h1>{response_content}</h1><form action='/' method='POST'><label for='destination'>Destination:</label><input type='text' id='destination' name='destination'><input type='submit' value='Submit'></form></body></html>"
        client_socket.sendall(response_data.encode())
    except Exception as e:
        print(f"Error handling request: {e}")
    finally:
        client_socket.close()


def process_form_data(destination, timetable, query_port, neighbours, station_name):
    if destination in timetable:
         return f"Direct route found: {timetable[destination]}"

    else:
        print(f"Destination not found: {destination}")

        message = create_message('QUERY',destination, station_name, query_port, 0, 4, query_port, "(" + station_name)

        ask_neighbours_about_destination(destination, query_port, neighbours, message, station_name)

        return "Looking for route..."
 
def create_message(msg_type, destination, source, source_port, hop_count, max_hops, sender, station_name):
    path=  station_name + "," + str(sender) + ")"
    return f"{msg_type}|{destination}|{source}|{source_port}|{hop_count}|{max_hops}|{sender}|{path}"


def parse_message(data):
    parts = data.split('|')
    
    return {
        'type': parts[0],
        'destination': parts[1],
        'source': parts[2],
        'source_port': parts[3],
        'hop_count': int(parts[4]),
        'max_hops': int(parts[5]),
        'sender': parts[6],
        'path': parts[7]
    }
 # Sends udp message to the specified host and port
def udp_client(message, host, port):
    print(f"Sending message: {message} to {host}:{port}")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
        try:
            client_socket.sendto(message.encode(), (host, port))
            print(f"Sent message to {host}:{port}")
        except Exception as e:
            print(f"Error sending to {host}:{port}: {e}")

def ask_neighbours_about_destination(destination, query_port, neighbours, message, station_name):
    for neighbour in neighbours:
        print(f"neighbour: {neighbour}")
        host, port = neighbour.split(':')
        udp_client(message, 'localhost', int(port))
 
#Recieves udp message

def udp_server(port, timetable, neighbours, seen_requests, station_name, allpossibleroutes):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        server_socket.bind(('localhost', port))
        print(f"UDP server listening on port {port}...")

        while True:
            data, address = server_socket.recvfrom(1024)
            message = parse_message(data.decode())
            repeatforwards =0
            
            if message['type'] == 'RESPONSE_TIMETABLE':
                
                message_id = message['sender']
                if message_id in pending_responses:
                    
                    pending_responses[message_id]['data'] = message['path']
                    pending_responses[message_id]['event'].set()
                print(f"Timetable response received: {message['path']} from {message['sender']}")
            if message['type'] == 'REQUEST_TIMETABLE':
                respond_with_timetable(message, timetable, port)

               
            else:
                print(f"Received message by {station_name}: {message}")
                request_id = f"{message['source']}-{message['destination']}"
                #for queries
                if message['destination']== station_name:
                    print("Destination reached. So forward message request ignored")
                else: 
                    print("message", message)
                    print("request_id", request_id)

                    if request_id in seen_requests:

                        print("Message already seen")
                        print("seen_requests[request_id]", seen_requests[request_id])
                    
                        

                    if message['type'] == 'QUERY' and (request_id not in seen_requests or seen_requests[request_id] < 5):
                        seen_requests[request_id] = seen_requests[request_id] + 1 if request_id in seen_requests else 1

                        if message['hop_count'] < message['max_hops']:
                            forward_message(message, neighbours, address, port, station_name)
                        if message['destination'] in timetable:
                            response = create_message('RESPONSE', message['destination'], station_name, message['source_port'], message['hop_count'], message['max_hops'], str(port), message['path'] + "," + "(" + station_name)
                            udp_client(response, 'localhost', int(message['source_port']))

                    elif message['type'] == 'RESPONSE':
                        message['path'] = message['path'] + "," + "(" + message['destination'] + "," +  'None' + ")"
                        allpossibleroutes.append(message['path'])
                        print("All possible routes discovered:", allpossibleroutes)
                        global response_timer
                        if response_timer is None:
                            response_timer = threading.Timer(10.0, process_discovered_routes, [route_discovery_done, allpossibleroutes, timetable])
                            response_timer.start()

def process_discovered_routes(route_discovery_done, allpossibleroutes, timetable):
    
    print("Timeout reached. Assuming all routes have been collected.")
    print("All possible routes discovered:")
    destination_reached_messages = []
    for route in allpossibleroutes:
        route_discovery_done.set()
        today = datetime.datetime.now().date()

    # Convert to epoch time
        start_time = integer_to_epoch_time(leave_time_int)
        x = epoch_to_time_only(start_time)
        print(f"Start time<><><><>: {x}")

        # Remove leading and trailing spaces, then split the string on "),"
        stations_ports = route.strip().split('),')

        # Clean each part and split into tuples of (station, port)
        stations_ports = [
            tuple(sp.strip().strip('()').split(',')) for sp in stations_ports
        ]

        # Cleaning up any whitespace around the elements in the tuple
        stations_ports = [
            (station.strip(), port.strip()) for station, port in stations_ports
        ]
        print(stations_ports)
        source_station, source_port = stations_ports[0]
        print(route)
        for i in range(len(stations_ports)):
            
            print("i", i)
            if i == len(stations_ports)-1:
                break
            current_station, current_port = stations_ports[(i)]
            next_station, next_port = stations_ports[int(i+1)]
            print("current_station", current_station)
            print("current_port", current_port) 
            print("next_station", next_station)
            print("next_port", next_port)
            
            '''if next_port == 'None' and i==len(stations_ports)-2:
                
                print("final i running yayaayayya")
                if next_station in timetable:
                    for detail in timetable[next_station]:
                        
                        departure_time_epoch = convert_to_epoch(detail['departure_time'])
                        #assuming time is in ascending order for routes
                        if departure_time_epoch > start_time:
                            print(f"Next departure from {current_station} to {next_station} at {detail['departure_time']}")
                            destinationreach = detail['arrival_time']
                            break
                        
                    print("Destination reached at", destinationreach, " through route", route)
                break
            '''
           
            if i == 0:
                print(f"Checking timetable for {current_station} to {next_station}")

                if next_station in timetable:
                    for detail in timetable[next_station]:
                        
                        departure_time_epoch = convert_to_epoch(detail['departure_time'])
                        #assuming time is in ascending order for routes
                        if departure_time_epoch > start_time:
                            print(f"Next departure from {current_station} to {next_station} at {detail['departure_time']}")
                            start_time = detail['arrival_time']
                            print(f"new start time = Arrival time: {detail['arrival_time']}")

                            break  # Break if the first available connection after the current time is found

            else:
                print("start time!!!", start_time)
                print(type(start_time))
                message_id, event = request_timetable(source_port, current_port, next_station, start_time)
                event.wait()  # Wait for the response
                print("check 2222")
                response_data = pending_responses.pop(message_id, None)
                if response_data and 'data' in response_data:
                    # Split the data to extract the departure time
                    data_parts = response_data['data'].split(',')
                    if len(data_parts) > 1:
                        departure_time = data_parts[0]  # This should be "20:00"
                        print(data_parts[2])
                        arrival_time = data_parts[2]  # This should be "20:30"
                        print("next_port", next_port and i==len(stations_ports)-2)
                        if next_port == 'None' and i==len(stations_ports)-2:
                            print("final i running")
                            if arrival_time[-1]== '\n':  
                                arrival_time = arrival_time[:-1]
                            time_reach = "Destination reached at " + arrival_time
                            route_message= str(time_reach +  " through route " + route)
                            destination_reached_messages.append(route_message)
                        else:
                            try:
                                print('is this working?')
                                start_time = arrival_time
                                print(f"New start time based on departure: {departure_time} is {start_time}")
                            except ValueError as e:
                                print(f"Error converting time: {departure_time}. Error: {e}")
                    else:
                        print("Error: Data format is incorrect. Expected at least two parts separated by commas.")
                print(f"Checking timetable for {current_station} to {next_station}")

    print("\n\n\n\n\nDestination reached messages:", destination_reached_messages) 
    calculate_best_route(destination_reached_messages)
                
                #current port will be the port we send this message to
                #next station will be the destination it looks for in it's timetable
                #start time will be the time we want to start from

def calculate_best_route(destination_reached_messages):
    
    best_time = "23:59"
    # Initialize a dictionary to store time as key and message as value
    time_message_dict = {}
    
    # Iterate over each message
    for message in destination_reached_messages:
        # Split message to find the time part, assuming the structure is consistent
        time_part = message.split(' ')[3]
        print("time_part", time_part)
        if time_part < best_time:
            best_time = time_part
        time_message_dict[message] = time_part  
    
    # Find the best route based on the earliest time
    best_route = [message for message, time in time_message_dict.items() if time == best_time]
    print("Best time:", best_time)
    print("Best route based on earliest time:", best_route)
        
def request_timetable(source_port, current_port, next_station, start_time):
    event = Event()
    message_id = f"{current_port}-{next_station}-{source_port}"
    pending_responses[message_id] = {'event': event, 'data': None}
    message = create_message('REQUEST_TIMETABLE', next_station, start_time, source_port, 0, 0, message_id, "0")
    udp_client(message, 'localhost', int(current_port),)

    return message_id, event

                        
def respond_with_timetable(message, timetable, port, ):
    
    destination = message['destination']
    print("!!!!", message['source'])
    message['source'] = message['source'].strip()
    print("!!!!", message['source'])
    try:
        start_time = convert_to_epoch(message['source'])
    except:
        print("typeee", type(message['source']))
        print("Time's already in epoch format")
        start_time = int(float((message['source'])))
    print(f"Responding with timetable for {destination} from {start_time}")
    source_port = message['source_port']
    message_id = message['sender']
    journey= ''
    if destination in timetable:
        for detail in timetable[destination]:
            departure_time_epoch = convert_to_epoch(detail['departure_time'])
            
        
            if departure_time_epoch > start_time:
                
                

                new_start_time = convert_to_epoch(detail['arrival_time'])
                journey= f"{detail['departure_time']}, Catch {detail['bus_train']},{detail['arrival_time']}\n"
                break
    
    response = create_message('RESPONSE_TIMETABLE', port, new_start_time, None, 0, 0, message_id, journey)
    #in response timetable, destination is not needed and second element is the station server instance port
    udp_client(response, 'localhost', int(message['source_port']))

def forward_message(message, neighbours, sender_address, port, station_name):
    new_hop_count = message['hop_count'] + 1
    new_path = message['path'] + "," + "(" + station_name 
    forwarded_message = create_message('QUERY',message['destination'], message['source'], message['source_port'], new_hop_count, message['max_hops'], port, new_path)

    for neighbour in neighbours:
        host, port = neighbour.split(':')
        print(f"localhost:{message['sender']}: {host}:{port}")
        if f"localhost:{message['sender']}" != f"{host}:{port}":
            udp_client(forwarded_message, host, int(port))


def main():
    if len(sys.argv) < 5:
        print("Usage: ./station-server.py station-name browser-port query-port neighbours... [format: host:port]")
        sys.exit(1)
    station_name = sys.argv[1]
    browser_port = int(sys.argv[2])
    query_port = int(sys.argv[3])
    neighbours = sys.argv[4:]
    seen_requests = {}  # Dictionary to keep track of seen requests to prevent loops
    allpossibleroutes = []
    global response_timer, route_discovery_done
    global pending_responses
    pending_responses = {}  # Initialize the dictionary
    # Load the timetable from a file assumed to be named 'tt-stationName.csv'
    
    with open('mywebpage.html', 'r') as file:
        webpage_content = file.read()
        leave_time_start = webpage_content.find('Leaving after ') + 14
        leave_time_end = webpage_content.find('</h3>', leave_time_start)
        leave_time_str = str(webpage_content[leave_time_start : leave_time_end])
        
        global leave_time_int
        leave_time_int = int(leave_time_str.replace(':', ''))
        leave_time_int *= 100
        print(integer_to_epoch_time(leave_time_int))
    
    
    
    timetable_filename = f"tt-{station_name}"
    timetable = read_timetable(timetable_filename)

    print(f"Station Name: {station_name}")
    print(f"Browser Port: {browser_port}")
    print(f"Query Port: {query_port}")
    print(f"Neighbours: {neighbours}")

    # Starting the HTTP and UDP servers in separate threads
    http_server_thread = threading.Thread(target=start_http_server, args=(browser_port, timetable, query_port, neighbours, station_name), daemon=True)
    udp_server_thread = threading.Thread(target=udp_server, args=(query_port, timetable, neighbours, seen_requests, station_name,allpossibleroutes ), daemon=True)
    
    http_server_thread.start()
    udp_server_thread.start()

    print("Servers are running. Press CTRL+C to exit.")

    # Keep the main thread running, wait for interrupt signal
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        
        print("Shutting down servers. Please wait...")
        if response_timer:
            response_timer.cancel()
        
    # Ensuring that all threads are joined before exiting
    http_server_thread.join()
    udp_server_thread.join()
    print("Servers have been shut down gracefully.")

if __name__ == "__main__":
    main()
