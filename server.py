import socket
import os
import struct
import threading
import subprocess
import json

HOST = '127.0.0.1'
PORT = 12000
BUFFER_SIZE = 1400
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
MAX_STORAGE_CAPACITY = 4 * 1024 * 1024 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def receive_data(conn, length):
    data = b''
    while len(data) < length:
        packet = conn.recv(length - len(data))
        if not packet:
            return None
        data += packet
    return data

def execute_ffmpeg(command):
    subprocess.run(command, capture_output=True, text=True)

def compress_video(input_path, output_path):
    command = ['ffmpeg', '-i', input_path, '-vcodec', 'libx264', '-crf', '28', output_path]
    execute_ffmpeg(command)

def change_resolution(input_path, output_path, resolution):
    command = ['ffmpeg', '-i', input_path, '-vf', f'scale={resolution}', '-c:a', 'copy', output_path]
    execute_ffmpeg(command)

def change_aspect_ratio(input_path, output_path, aspect_ratio):
    command = ['ffmpeg','-i', input_path,'-vf', f'setdar={aspect_ratio}', '-c:a', 'copy', output_path]
    execute_ffmpeg(command)

def extract_audio(input_path, output_path):
    command = ['ffmpeg', '-i', input_path, '-q:a', '0', '-map', 'a', output_path]
    execute_ffmpeg(command)

def create_gif(input_path, output_path, start_time, duration):
    command = ['ffmpeg', '-i', input_path, '-ss', start_time, '-t', duration, '-vf', 'fps=10,scale=320:-1:flags=lanczos', output_path]
    execute_ffmpeg(command)

def create_webm(input_path, output_path, start_time, duration):
    command = ['ffmpeg', '-i', input_path, '-ss', start_time, '-t', duration, '-c:v', 'libvpx', '-b:v', '1M', '-c:a', 'libvorbis', output_path]
    execute_ffmpeg(command)

def send_error(conn, code, description, solution):
    try:
        error_message = json.dumps({
            "code": code,
            "description": description,
            "solution": solution
        }).encode()
        length = len(error_message)
        conn.sendall(struct.pack('!HB5s', length, 0, (0).to_bytes(5, byteorder='big')))
        conn.sendall(error_message)
    except BrokenPipeError:
        print("クライアントへの接続が失われました。")

def get_total_storage_used():
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(UPLOAD_FOLDER):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size

def handle_client(conn):
    try:
        header = receive_data(conn, 8)  # 8バイトのヘッダーを受信
        if not header:
            send_error(conn, 400, "Bad Request", "ヘッダーの受信に失敗しました。")
            return
        
        json_size, media_type_size, payload_size_bytes = struct.unpack("!HB5s", header)
        payload_size = int.from_bytes(payload_size_bytes, byteorder='big')

        json_data = receive_data(conn, json_size).decode()
        json_args = json.loads(json_data)

        media_type = receive_data(conn, media_type_size).decode()

        filename = json_args.get('filename', 'uploaded_file')
        operation = json_args.get('operation')
        options = json_args.get('options', {})
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        current_storage = get_total_storage_used()
        if current_storage + payload_size > MAX_STORAGE_CAPACITY:
            send_error(conn, 507, 'Storage Full', "アップロードするためのサーバーの容量が足りません。")
            return

        with open(filepath, 'wb') as f:
            receive_size = 0
            while receive_size < payload_size:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    send_error(conn, 400, "Bad Request", "ファイルのアップロードに失敗しました")
                    return
                f.write(data)
                receive_size += len(data)

        output_filename = ""
        output_filepath = ""

        try:
            match media_type:
                case 'mp4' | 'avi':
                    match operation:
                        case 'compress':
                            output_filename = f"compress_{filename}"
                            output_filepath = os.path.join(OUTPUT_FOLDER, output_filename)
                            compress_video(filepath, output_filepath)

                        case 'change_resolution':
                            resolution = options["resolution"]
                            output_filename = f"resolution_{resolution}_{filename}"
                            output_filepath = os.path.join(OUTPUT_FOLDER, output_filepath)
                            change_resolution(filepath, output_filepath, resolution)

                        case 'change_aspect_ratio':
                            aspect_ratio = options['aspect_ratio']
                            output_filename = f"aspect_ratio_{aspect_ratio}_{filename}"
                            output_filepath = os.path.join(OUTPUT_FOLDER, output_filepath)
                            change_aspect_ratio(filepath, output_filepath, aspect_ratio)

                        case 'extract_audio':
                            output_filename = f"{os.path.splitext(filename)[0]}.mp3"
                            output_filepath = os.path.join(OUTPUT_FOLDER, output_filename)
                            extract_audio(filepath, output_filepath)

                        case 'create_gif':
                            start_time = options['start_time']
                            duration = options['duration']
                            output_filename = f"{os.path.splitext(filename)[0]}.gif"
                            output_filepath = os.path.join(OUTPUT_FOLDER, output_filepath)
                            create_gif(filepath, output_filepath, start_time, duration)

                        case 'create_webm':
                            start_time = options['start_time']
                            duration = options['duration']
                            output_filename = f"{os.path.splitext(filename)[0]}.webm"
                            output_filepath = os.path.join(OUTPUT_FOLDER, output_filepath)
                            create_webm(filepath, output_filepath, start_time, duration)

                        case _:
                            send_error(conn, 400, "Bad Request", f"Unknown operation: {operation}")

                case 'mp3':
                    send_error(conn, 400, "Bad Request", "mp3ファイルはサポートされていません。")
                    return
                
        except Exception as e:
            send_error(conn, 500, "Internal server error", str(e))
            return
        
        # Output filename and file size to be sent to the client
        output_filename_bytes = output_filename.encode()
        output_filename_size = len(output_filename_bytes)
        output_size = os.path.getsize(output_filepath)
        
        # Send the output filename size, output filename, and output file size
        conn.sendall(struct.pack('!I', output_filename_size))
        conn.sendall(output_filename_bytes)
        conn.sendall(struct.pack('!I', output_size))

        with open(output_filepath, 'rb') as f:
            while (chunk := f.read(BUFFER_SIZE)):
                conn.sendall(chunk)
        print(f"送信：{output_filename}（サイズ：{output_size}バイト）")

    except Exception as e:
        send_error(conn, 500, "Internal Server Error", str(e))
    finally:
        conn.close()

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"{HOST}:{PORT}で接続を待ってます。")

        def exit_listener():
            exitServer = input("'exit'でサーバーを終了します。")
            if exitServer == "exit":
                print("サーバーを終了します。")
                os._exit(0)

        threading.Thread(target=exit_listener, daemon=True).start()

        while True:
            conn, addr = s.accept()
            print(f"{addr}と接続しました。")
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

if __name__ == '__main__':
    start_server()
