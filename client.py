import socket
import os
import struct
import json
import time

HOST = '127.0.0.1'  # サーバーのホスト名またはIPアドレス
PORT = 12000
BUFFER_SIZE = 1400
CHECK_INTERVAL = 60

def send_file():
    while True:
        filepath = input("アップロードするファイルのパスを入力してください。\n'exit'と入力すると終了します。")
        if filepath == "exit":
            print("クライアントを終了します。")
            break

        if not os.path.exists(filepath):
            print(f"{filepath}ファイルが存在しません。")
            continue
        
        if not filepath.endswith(".mp4"):
            print(f"{filepath}はmp4ファイルではありません。")
            continue

        operation = input("実行する操作を選択し入力してください。\n（compress, change_resolution, change_aspect_ratio, extract_audio, create_gif, create_webm）:")
        options = {}
        if operation == 'change_resolution':
            options['resolution'] = input("希望する解像度を入力してください。（例： 640✕480）:")
        elif operation == 'change_aspect_ratio':
            options['aspect_ratio'] = input("希望するアスペクト比を入力してください。（例： 16:9）:")
        elif operation in ['create_gif', 'create_webm']:
            options['start_time'] = input("開始時間を入力してください。（例： 00:00:00）:")
            options['duration'] = input("長さを秒単位で入力してください。（例： 5）:")

        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        json_args = json.dumps({"filename": filename, "operation": operation, "options": options}).encode()
        json_size = len(json_args)
        media_type = os.path.splitext(filename)[1][1:]
        media_type_bytes = media_type.encode()
        media_type_size = len(media_type_bytes)
        payload_size = filesize

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                payload_size_bytes = payload_size.to_bytes(5, byteorder='big')
                header = struct.pack('!HB5s', json_size, media_type_size, payload_size_bytes)
                s.sendall(header)
                s.sendall(json_args)
                s.sendall(media_type_bytes)

                with open(filepath, 'rb') as f:
                    while (chunk := f.read(BUFFER_SIZE)):
                        s.sendall(chunk)
                    print(f"{filename}の送信に成功しました。")

                    # Receive the output filename size
                    output_filename_size = struct.unpack('!I', s.recv(4))[0]
                    # Receive the output filename
                    output_filename = s.recv(output_filename_size).decode()
                    print(f"受信したファイル名: {output_filename}")

                    # Receive the output file size
                    output_filesize = struct.unpack('!I', s.recv(4))[0]
                    if output_filesize == 0:
                        error_data = s.recv(1024).decode()
                        error_json = json.loads(error_data)
                        print(f"エラーが発生しました：{error_json['description']}")
                        print(f"解決策：{error_json['solution']}")
                        break

                    output_filepath = os.path.join("downloads", output_filename)
                    os.makedirs("downloads", exist_ok=True)
                    with open(output_filepath, 'wb') as f:
                        received_size = 0
                        while received_size < output_filesize:
                            chunk = s.recv(BUFFER_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                            received_size += len(chunk)
                    print(f"{output_filepath}の受信に成功しました")
                    break

        except Exception as e:
            print(f"ファイル送信中にエラーが発生しました：{e}")

if __name__ == '__main__':
    send_file()
