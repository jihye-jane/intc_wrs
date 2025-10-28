# logging/data_logger.py
"""
모든 센서 데이터와 제어 출력값을 수집하여 파일로 저장하는 데이터 로거 모듈입니다.
별도의 스레드에서 동작하며, Queue를 통해 스레드에 안전하게 데이터를 수신합니다.
"""

import threading
import queue
import csv
import os
import time
import config

class DataLogger(threading.Thread):
    def __init__(self):
        """
        DataLogger 스레드를 초기화하고, 로그 파일을 저장할 디렉토리와 파일을 준비합니다.
        """
        super().__init__()
        self.daemon = True
        self.running = True
        
        # 스레드 간 안전한 데이터 교환을 위한 큐(Queue)
        self.data_queue = queue.Queue()

        # --- 로그 파일 및 디렉토리 준비 ---
        try:
            # 로그를 저장할 기본 디렉토리 생성 (없으면)
            if not os.path.exists(config.LOG_BASE_DIR):
                os.makedirs(config.LOG_BASE_DIR)
            
            # 이미지를 저장할 하위 디렉토리 생성 (없으면)
            if not os.path.exists(config.LOG_IMAGE_DIR_PATH):
                os.makedirs(config.LOG_IMAGE_DIR_PATH)

            # CSV 로그 파일 열기 (이어쓰기가 아닌, 실행 시마다 새로 생성 'w')
            # (!!!) 기존 로그를 보존하려면 'w'를 'a'(append)로 변경
            self.csv_file = open(config.LOG_CSV_FILE_PATH, 'w', newline='', encoding='utf-8')
            
            # CSV 작성을 위한 DictWriter 준비 (헤더는 첫 데이터 수신 후 동적 결정)
            self.csv_writer = None
            self.csv_headers = []
            
            print(f"[Logger] 로거 초기화 완료. 로그 경로: '{config.LOG_BASE_DIR}/'")

        except Exception as e:
            print(f"[Logger] 치명적 에러: 로그 파일/디렉토리 준비 실패: {e}")
            self.running = False # 로거 실행 불가

    def log_data(self, data_dict):
        """
        다른 스레드(센서, 컨트롤러 등)에서 이 함수를 호출하여 로깅할 데이터를 큐에 추가합니다.
        :param data_dict: {'type': '...', 'timestamp': ..., 'key': value, ...} 형식의 딕셔너리
        """
        if self.running and config.LOG_ENABLE:
            try:
                self.data_queue.put_nowait(data_dict)
            except queue.Full:
                print("[Logger] 경고: 데이터 큐가 가득 찼습니다. 일부 로그가 유실될 수 있습니다.")

    def run(self):
        """스레드가 시작되면 실행되는 메인 로깅 루프"""
        print("[Logger] 데이터 로깅 스레드 시작.")
        
        while self.running:
            try:
                # 큐에서 데이터가 들어올 때까지 최대 1초 대기
                data = self.data_queue.get(timeout=1.0)
                
                # --- CSV 헤더 처리 ---
                # 첫 데이터이거나, 기존에 없던 새로운 키(열)가 포함된 데이터가 들어오면 헤더 업데이트
                if self.csv_writer is None or not set(data.keys()).issubset(self.csv_headers):
                    # 기존 헤더에 새로운 키 추가
                    self.csv_headers.extend([k for k in data.keys() if k not in self.csv_headers])
                    
                    # DictWriter를 새로운 헤더로 다시 생성
                    self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=self.csv_headers)
                    
                    # 파일의 맨 처음이라면 헤더 쓰기
                    if self.csv_file.tell() == 0:
                        self.csv_writer.writeheader()

                # --- 데이터 쓰기 ---
                # 헤더에 정의된 필드만 골라서 CSV 파일에 한 줄 기록
                self.csv_writer.writerow({k: v for k, v in data.items() if k in self.csv_headers})
                
                # (중요) 버퍼를 비워 파일에 즉시 쓰도록 함 (실시간 확인용)
                self.csv_file.flush()
                
            except queue.Empty:
                # 1초 동안 큐에 데이터가 없으면 그냥 계속 진행
                # (프로그램 종료를 위해 필요)
                continue
            except Exception as e:
                print(f"[Logger] 에러: 로깅 루프 중 예외 발생: {e}")

        # --- 스레드 종료 처리 ---
        self.stop()
        print("[Logger] 데이터 로깅 스레드 종료 완료.")

    def stop(self):
        """스레드를 안전하게 종료시키기 위해 호출하는 함수"""
        if not self.running:
            return # 이미 종료된 경우 중복 실행 방지
            
        print("[Logger] 종료 신호 수신. 남은 데이터를 처리합니다...")
        self.running = False
        
        # 큐에 남아있는 모든 데이터를 파일에 기록
        while not self.data_queue.empty():
            try:
                data = self.data_queue.get_nowait()
                if self.csv_writer:
                    self.csv_writer.writerow({k: v for k, v in data.items() if k in self.csv_headers})
            except queue.Empty:
                break
            except Exception as e:
                print(f"[Logger] 종료 중 로깅 에러: {e}")

        # 파일 닫기
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            print("[Logger] 로그 파일 닫기 완료.")
