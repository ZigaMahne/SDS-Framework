# Copyright (c) 2023 Arm Limited. All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the License); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# SDS I/O Server

import argparse
import sys

import os.path as path
import serial
import ipaddress
import ifaddr
import socket
import errno

# SDS I/O Manager
class sdsio_manager:
    def __init__(self, out_dir):
        self.stream_identifier = 0
        self.stream_files = {}
        self.out_dir = path.normpath(f"{out_dir}")

    # Open
    def __open(self, mode, name):
        response = bytearray()
        file_index         = 0
        invalid_name       = 0
        response_stream_id = 0
        response_command   = 1
        response_data_size = 0

        # Validate name
        if len(name) == 0:
            invalid_name = 1
        else:
            invalid_chars = [chr(0x00), chr(0x01), chr(0x02), chr(0x03),
                             chr(0x04), chr(0x05), chr(0x06), chr(0x07),
                             chr(0x08), chr(0x09), chr(0x0A), chr(0x0B),
                             chr(0x0C), chr(0x0D), chr(0x0E), chr(0x0F),
                             chr(0x7F), '\"', '*', '/', ':', '<', '>', '?', '\\', '|']
            for ch in invalid_chars:
                if name.find(ch) != -1:
                    invalid_name = 1
                    break

        if invalid_name == 1:
            print(f"Invalid stream name: {name}\n")
        else:
            if mode == 1:
                # Write mode
                fname = path.join(self.out_dir, f"{name}.{file_index}.sds")
                while path.exists(fname) == True:
                    file_index = file_index + 1
                    fname = path.join(self.out_dir, f"{name}.{file_index}.sds")
                try:
                    f = open(fname, "wb")
                    self.stream_identifier += 1
                    self.stream_files.update({self.stream_identifier: f})
                    response_stream_id = self.stream_identifier
                except Exception as e:
                    print(f"Could not open file {fname}. Error: {e}\n")
                    return 0

            # if mode == 0:
            #     read mode not supported

        response.extend(response_command.to_bytes(4, byteorder='little'))
        response.extend(response_stream_id.to_bytes(4, byteorder='little'))
        response.extend(mode.to_bytes(4, byteorder='little'))
        response.extend(response_data_size.to_bytes(4, byteorder='little'))
        return response

    # Close
    def __close(self, id):
        response = bytearray()

        try:
            self.stream_files.get(id).close()
            self.stream_files.pop(id)
        except Exception as e:
            print(f"Could not close file {self.stream_files.get(id)}. Error: {e}\n")
        return response

    # Write
    def __write(self, id, data):
        response = bytearray()

        try:
            self.stream_files.get(id).write(data)
        except Exception as e:
            print(f"Could not write to file {self.stream_files.get(id)}. Error: {e}\n")
        return response

    # Clear
    def clear(self):
        id_list = list()
        for id in self.stream_files:
            id_list.append(id)
        for id in id_list:
            self.__close(id)

    # Execute request
    def execute_request (self, request_buf):
        response = bytearray()

        command   = int.from_bytes(request_buf[0:4],   'little')
        sdsio_id  = int.from_bytes(request_buf[4:8],   'little')
        argument  = int.from_bytes(request_buf[8:12],  'little')
        data_size = int.from_bytes(request_buf[12:16], 'little')
        data      = request_buf[16:16 + data_size]

        # Open
        if command == 1:
            response = self.__open(argument, data.decode('utf-8').split("\0")[0])
        # Close
        elif command == 2:
            self.__close(sdsio_id)
        # Write
        elif command == 3:
            self.__write(sdsio_id, data)
        # Invalid command
        else:
            print(f"Invalid command: {command}\n")
        return response

# Server - Socket
class sdsio_server_socket:
    def __init__(self, ip, interface, port):
        self.ip             = ip
        self.port           = port
        self.sock_listening = None
        self.sock           = None

        if interface != None:
            ipv6 = None
            adapter_list = ifaddr.get_adapters()
            for adapter in adapter_list:
                if adapter.name == interface or adapter.nice_name == interface:
                    for ips in adapter.ips:
                        try:
                            socket.inet_pton(socket.AF_INET, ips.ip)
                            self.ip = ips.ip
                        except:
                            try:
                                socket.inet_pton(socket.AF_INET6, ips.ip[0])
                                ipv6 = ips.ip[0]
                            except:
                                break
            if self.ip == None:
                self.ip = ipv6
        if self.ip == None:
            self.ip = ip = socket.gethostbyname(socket.gethostname())
        print(f"  Server IP: {self.ip}\n")

    # socket accept
    def __accept(self):
        while True:
            try:
                # Accept
                self.sock, addr = self.sock_listening.accept()
                self.sock.setblocking(False)
                break
            except Exception as e:
                if (e.errno == errno.EWOULDBLOCK) or (e.errno == errno.EAGAIN):
                    continue
                else:
                    print(f"Server open error: {e.errno}\n")
                    sys.exit(1)

    # Open socket server
    def open(self):
        try:
            # Create TCP socket
            self.sock_listening = socket.socket(socket.AF_INET,     # Internet
                                                socket.SOCK_STREAM) # TCP
            self.sock_listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock_listening.bind((self.ip, self.port))
            self.sock_listening.listen()
            self.sock_listening.setblocking(False)
        except Exception as e:
            print(f"Server open error: {e}\n")
            sys.exit(1)

        self.__accept()

    # Close socket server
    def close(self):
        self.sock.close()
        self.sock_listening.close()

    # Read
    def read(self, size):
        try:
            data = self.sock.recv(size)
            if data:
                return data
            else:
                self.__accept()
        except Exception as e:
            if (e.errno == errno.EWOULDBLOCK) or (e.errno == errno.EAGAIN):
                return None
            else:
                print(f"Server read error: {e}\n")
                sys.exit(1)

    # Write
    def write(self, data):
        size = 0
        try:
            size = self.sock.send(data)
        except Exception as e:
            if (e.errno == errno.EWOULDBLOCK) or (e.errno == errno.EAGAIN):
                return size
            else:
                print(f"Server write error: {e}\n")
                sys.exit(1)

# Server - Serial
class sdsio_server_serial:
    def __init__(self, port, baudrate, parity, stop_bits):
        self.port      = port
        self.baudrate  = baudrate
        self.parity    = parity
        self.stop_bits = stop_bits
        self.ser  = 0

    # Open serial port
    def open (self):
        print(f"  Serial Port: {self.port}\n")
        try:
            self.ser = serial.Serial()
            if sys.platform != "darwin":
                if 'COM' in self.port:
                    self.ser.port = self.port
                else:
                    self.ser.port = f"COM{self.port}"
            else:
                self.ser.port = f"dev/tty{self.port}"
            self.ser.baudrate = self.baudrate
            self.ser.parity   = self.parity
            self.ser.stopbits = self.stop_bits
            self.ser.timeout  = 0
            self.ser.open()
        except Exception as e:
            print(f"Server open error: {e}\n")
            sys.exit(1)

    # Close serial port
    def close(self):
        self.ser.close()

    # Read
    def read(self, size):
        try:
            return self.ser.read(size)
        except Exception as e:
            print(f"Serial read error: {e}\n")
            sys.exit(1)

    # Write
    def write(self, data):
        try:
            size = self.ser.write(data)
            if size:
              return size
            else:
                return None
        except Exception as e:
            print(f"Serial write error: {e}\n")
            sys.exit(1)

# Validate directory path
def dir_path(out_dir):
    if path.isdir(out_dir):
        return out_dir
    else:
        raise argparse.ArgumentTypeError(f"Invalid output directory: {out_dir}!")

# Validate IP address
def ip(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip
    except:
        raise argparse.ArgumentTypeError(f"Invalid IP address: {ip}!")

# Validate Network interface
def interface(interface):
    i = None
    try:
        adapter_list = ifaddr.get_adapters()
        for adapter in adapter_list:
            name = adapter.name.replace('{', '')
            name = name.replace('}', '')
            nice_name = adapter.nice_name.replace('{', '')
            nice_name = nice_name.replace('}', '')
            if name == interface:
                return name
            if nice_name == interface:
                return nice_name
    except:
        pass
    raise argparse.ArgumentTypeError(f"Invalid network interface: {interface}!")


# parse arguments
def parse_arguments():
    formatter = lambda prog: argparse.HelpFormatter(prog, max_help_position=41)
    parser = argparse.ArgumentParser(formatter_class=formatter, description="SDS I/O server")

    subparsers = parser.add_subparsers(dest="server_type", required=True)

    parser_socket = subparsers.add_parser("socket", formatter_class=formatter)
    parser_socket_optional = parser_socket.add_argument_group("optional")
    parser_socket_optional_exclusive = parser_socket_optional.add_mutually_exclusive_group()
    parser_socket_optional_exclusive.add_argument("--ipaddr", dest="ip",  metavar="<IP>",
                                        help="Server IP address (not allowed with argument --interface)", type=ip, default=None)
    parser_socket_optional_exclusive.add_argument("--interface", dest="interface",  metavar="<Interface>",
                                        help="Network interface (not allowed with argument --ipaddr)", type=interface, default=None)
    parser_socket_optional.add_argument("--port", dest="port",  metavar="<TCP Port>",
                                        help="TCP port (default: 5050)", type=int, default=5050)
    parser_socket_optional.add_argument("--outdir", dest="out_dir", metavar="<Output dir>",
                                        help="Output directory", type=dir_path, default=".")

    parser_serial = subparsers.add_parser("serial", formatter_class=formatter)
    parser_serial_required = parser_serial.add_argument_group("required")
    parser_serial_required.add_argument("-p", dest="port", metavar="<Serial Port>",
                                        help="Serial port", required=True)
    parser_serial_optional = parser_serial.add_argument_group("optional")
    parser_serial_optional.add_argument("--baudrate", dest="baudrate",  metavar="<Baudrate>",
                                        help="Baudrate (default: 115200)", type=int, default=115200)

    help_str = "Parity: "
    for key, value in serial.PARITY_NAMES.items():
        help_str += f"{key} = {value}, "
    help_str = help_str[:-2]
    help_str += f" (default: {serial.PARITY_NONE})"
    parser_serial_optional.add_argument("--parity", dest="parity",  metavar="<Parity>", choices=serial.PARITY_NAMES.keys(),
                                        help=help_str, default=serial.PARITY_NONE)
    help_str = f"Stop bits: {serial.STOPBITS_ONE}, {serial.STOPBITS_ONE_POINT_FIVE}, {serial.STOPBITS_TWO} (default: {serial.STOPBITS_ONE})"
    parser_serial_optional.add_argument("--stopbits", dest="stop_bits",  metavar="<Stop bits>", type=float,
                                        choices=[serial.STOPBITS_ONE, serial.STOPBITS_ONE_POINT_FIVE, serial.STOPBITS_TWO],
                                        help=help_str, default=serial.STOPBITS_ONE)
    parser_serial_optional.add_argument("--outdir", dest="out_dir", metavar="<Output dir>",
                                        help="Output directory", type=dir_path, default=".")

    return parser.parse_args()

# main
def main():

    args = parse_arguments()

    stream_buf_cnt   = 0

    header_size      = 16
    header_buf       = bytearray()

    request_buf_size = 0
    request_buf      = bytearray()

    manager = sdsio_manager(args.out_dir)

    if args.server_type == "socket":
        server = sdsio_server_socket(args.ip, args.interface, args.port)
    elif args.server_type == "serial":
        server = sdsio_server_serial(args.port, args.baudrate, args.parity, args.stop_bits)

    try:
        print("Server opening...\n")
        server.open()
        print("Server Opened.\n")

        while True:

            stream_buf = server.read(8192)
            stream_buf_cnt = 0

            while stream_buf != None and stream_buf_cnt < len(stream_buf):

                if request_buf_size == 0:
                    # Request buffer is empty. Get new request
                    cnt = header_size - len(header_buf)
                    if cnt > (len(stream_buf) - stream_buf_cnt):
                        cnt = len(stream_buf) - stream_buf_cnt
                    header_buf.extend(stream_buf[stream_buf_cnt: stream_buf_cnt + cnt])
                    stream_buf_cnt += cnt

                    if len(header_buf) != header_size:
                        # Header not complete. Read new data
                        break
                    else:
                        # New request
                        request_buf = bytearray()
                        request_buf.extend(header_buf)
                        request_buf_size = int.from_bytes(header_buf[12:16], 'little') + header_size
                        # Clear Header buffer
                        del header_buf[0:]

                cnt = request_buf_size - len(request_buf)
                if cnt > (len(stream_buf) - stream_buf_cnt):
                    # Not all data is yet available.
                    cnt = len(stream_buf) - stream_buf_cnt

                # Copy request data
                request_buf.extend(stream_buf[stream_buf_cnt : stream_buf_cnt + cnt])

                # Update data count
                stream_buf_cnt += cnt

                if len(request_buf) == request_buf_size:
                    # Whole request is prepared. Execute request.
                    response = manager.execute_request(request_buf)

                    # Reset request buffer size. New request can now be processed.
                    request_buf_size = 0

                    # Send response
                    if response:
                        try:
                            server.write(bytes(response))
                        except socket.error as e:
                            print(f"Socket send error: {e}\n")
                            sys.exit(1)

    except KeyboardInterrupt:
        try:
            server.close()
        except Exception:
            # If server.close() raises an exception, don't print the error
            pass
        manager.clear()
        print("\nExit\n")
        sys.exit(0)

# main
if __name__ == '__main__':
    print("Press Ctrl+C to exit.\n")
    main()
