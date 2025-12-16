# coding:UTF-8
"""
WitMotion IMU 센서를 BLE를 통해 스캔, 연결하고 데이터를 수신하는 통합 스크립트입니다.
bleak 라이브러리와 asyncio를 사용합니다.
"""

import time
import bleak
import asyncio
import sys # 사용자 입력 처리 개선을 위해 추가

# -----------------------------------------------------------------
# 1. DeviceModel 클래스 (BLE 연결, 통신, 데이터 파싱 담당)
# -----------------------------------------------------------------

# 장치 인스턴스 Device instance
class DeviceModel:
    # region UUID 상수 (WitMotion BLE)
    # 실제 장치에 따라 다를 수 있으므로 확인 필요
    TARGET_SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9a34fb"
    TARGET_CHAR_UUID_READ = "0000ffe4-0000-1000-8000-00805f9a34fb" # Notify Characteristic
    TARGET_CHAR_UUID_WRITE = "0000ffe9-0000-1000-8000-00805f9a34fb" # Write Characteristic
    # endregion

    # region 属性 attribute
    deviceName = "나의 장치"
    deviceData = {}
    
    # 연결 상태를 나타내는 asyncio.Event
    _connect_event = None
    # endregion

    def __init__(self, deviceName, mac, callback_method):
        print("[Model] 디바이스 모델 초기화 중...")
        self.deviceName = deviceName
        self.mac = mac
        self.client = None
        self.writer_characteristic_uuid = None
        self.isOpen = False
        self.callback_method = callback_method
        self.deviceData = {}
        self.TempBytes = [] # 임시 바이트 배열 초기화

    # region 데이터 Getter/Setter
    def set(self, key, value):
        self.deviceData[key] = value

    def get(self, key):
        if key in self.deviceData:
            return self.deviceData[key]
        else:
            return None
            
    def remove(self, key):
        del self.deviceData[key]
    # endregion

    # 장치 열기 open Device
    async def openDevice(self):
        print(f"[Model] {self.mac}에 연결 시도 중...")
        
        try:
            # 10초 타임아웃 설정
            async with bleak.BleakClient(self.mac, timeout=10.0) as client:
                self.client = client
                self.isOpen = True
                self._connect_event = asyncio.Event()

                notify_characteristic = None
                
                print("[Model] 서비스 탐색 중...")
                
                service = client.services.get_service(self.TARGET_SERVICE_UUID)
                if service:
                    print(f"[Model] 서비스 찾음: {service.uuid}")
                    notify_characteristic = service.get_characteristic(self.TARGET_CHAR_UUID_READ)
                    writer_char = service.get_characteristic(self.TARGET_CHAR_UUID_WRITE)
                    
                    if writer_char:
                        self.writer_characteristic_uuid = writer_char.uuid
                    
                if notify_characteristic:
                    print(f"[Model] Notify Characteristic 찾음: {notify_characteristic.uuid}")
                    
                    # 1. 알림 설정 Set up notifications
                    await client.start_notify(notify_characteristic.uuid, self.onDataReceived)

                    # 2. 연결 상태 유지 (데이터 수신 대기)
                    print("[Model] 연결 성공. 데이터 수신 대기 중 (Ctrl+C를 눌러 종료)...")
                    
                    # 루프가 종료될 때까지 무한정 대기
                    await self._connect_event.wait() 
                    
                else:
                    print("[Model] 일치하는 Notify/Write Characteristic을 찾을 수 없습니다.")

        except bleak.exc.BleakError as e:
            print(f"[Model] [BLE 오류] 장치 연결 또는 통신 실패: {e}")
        except Exception as e:
            print(f"[Model] [심각한 오류] 예기치 않은 오류 발생: {e}")
        finally:
            if self.isOpen:
                self.isOpen = False
            self.client = None
            print("[Model] 장치 연결이 종료되었습니다.")


    # 장치 닫기 close Device
    async def closeDevice(self):
        self.isOpen = False
        if self._connect_event:
            self._connect_event.set() # 대기 중인 openDevice 루프를 종료
        print("[Model] 장치가 꺼졌습니다.")

    # region 데이터 분석 data analysis
    
    # 시리얼 포트 데이터 처리  Serial port data processing
    def onDataReceived(self, sender, data):
        """BLE 알림 데이터 수신 시 호출되는 콜백."""
        self.TempBytes.extend(data) 

        while self.TempBytes:
            # 1. 시작 바이트 (0x55) 찾기
            if self.TempBytes[0] != 0x55:
                del self.TempBytes[0]
                continue
            
            # 2. 충분한 바이트 확인 (최소 2바이트)
            if len(self.TempBytes) < 2:
                break 

            # 3. 패킷 타입 확인 (0x55 0x61 - WitMotion 가속도/각속도/각도 패킷으로 가정)
            if self.TempBytes[1] != 0x61:
                del self.TempBytes[0] # 0x55 바이트를 버리고 다음 0x55를 찾는다
                continue

            # 4. 전체 패킷 길이 확인 (0x55 0x61 + 18바이트 데이터 + 2바이트 체크섬 = 22바이트)
            FULL_PACKET_LENGTH = 22
            
            if len(self.TempBytes) < FULL_PACKET_LENGTH:
                break # 데이터 부족, 다음 알림 대기

            # 5. 패킷 추출
            packet = self.TempBytes[:FULL_PACKET_LENGTH]

            # 6. 데이터 분석 (헤더 2바이트 제외, 20바이트 데이터)
            self.processData(packet[2:])
            
            # 7. 처리된 패킷 제거
            del self.TempBytes[:FULL_PACKET_LENGTH]

    # 데이터 분석 data analysis (Bytes는 20바이트)
    def processData(self, Bytes):
        Ax = self.getSignInt16(Bytes[1] << 8 | Bytes[0]) / 32768 * 16
        Ay = self.getSignInt16(Bytes[3] << 8 | Bytes[2]) / 32768 * 16
        Az = self.getSignInt16(Bytes[5] << 8 | Bytes[4]) / 32768 * 16
        Gx = self.getSignInt16(Bytes[7] << 8 | Bytes[6]) / 32768 * 2000
        Gy = self.getSignInt16(Bytes[9] << 8 | Bytes[8]) / 32768 * 2000
        Gz = self.getSignInt16(Bytes[11] << 8 | Bytes[10]) / 32768 * 2000
        AngX = self.getSignInt16(Bytes[13] << 8 | Bytes[12]) / 32768 * 180
        AngY = self.getSignInt16(Bytes[15] << 8 | Bytes[14]) / 32768 * 180
        AngZ = self.getSignInt16(Bytes[17] << 8 | Bytes[16]) / 32768 * 180
        
        self.set("AccX", round(Ax, 3))
        self.set("AccY", round(Ay, 3))
        self.set("AccZ", round(Az, 3))
        self.set("AsX", round(Gx, 3))
        self.set("AsY", round(Gy, 3))
        self.set("AsZ", round(Gz, 3))
        self.set("AngX", round(AngX, 3))
        self.set("AngY", round(AngY, 3))
        self.set("AngZ", round(AngZ, 3))
        
        # 콜백 호출
        self.callback_method(self)

    # int16 부호 있는 정수 얻기 Obtain int16 signed number
    @staticmethod
    def getSignInt16(num):
        if num >= pow(2, 15):
            num -= pow(2, 16)
        return num

    # endregion

    # 시리얼 포트 데이터 전송 Sending serial port data
    async def sendData(self, data: bytes):
        try:
            if self.client and self.writer_characteristic_uuid:
                await self.client.write_value(self.writer_characteristic_uuid, data)
        except Exception as ex:
            print(f"[Model] [Send Data Error] {ex}")

    # 레지스터 읽기 read register
    async def readReg(self, regAddr: int):
        await self.sendData(self.get_readBytes(regAddr))

    # 레지스터 쓰기 Write Register
    async def writeReg(self, regAddr: int, sValue: int):
        await self.unlock()
        # --- 💡 개선: time.sleep -> asyncio.sleep으로 변경 ---
        await asyncio.sleep(0.1) 
        
        await self.sendData(self.get_writeBytes(regAddr, sValue))
        
        # --- 💡 개선: time.sleep -> asyncio.sleep으로 변경 ---
        await asyncio.sleep(0.1) 
        
        await self.save()

    # 읽기 명령 캡슐화 Read instruction encapsulation
    @staticmethod
    def get_readBytes(regAddr: int) -> bytes:
        tempBytes = [0xff, 0xaa, 0x27, regAddr, 0]
        return bytes(tempBytes)

    # 쓰기 명령 캡슐화 Write instruction encapsulation
    @staticmethod
    def get_writeBytes(regAddr: int, rValue: int) -> bytes:
        tempBytes = [0xff, 0xaa, regAddr, rValue & 0xff, (rValue >> 8) & 0xff]
        return bytes(tempBytes)

    # 잠금 해제 unlock
    async def unlock(self):
        cmd = self.get_writeBytes(0x69, 0xb588)
        await self.sendData(cmd)

    # 저장 save
    async def save(self):
        cmd = self.get_writeBytes(0x00, 0x0000)
        await self.sendData(cmd)


# -----------------------------------------------------------------
# 2. 메인 스크립트 로직 (스캔, 선택, 연결 실행)
# -----------------------------------------------------------------

# Global 변수
devices = []
last_print_time = time.time() # 데이터 출력 주기를 제어하기 위한 변수

# 데이터 업데이트 시 호출될 함수 This method will be called when data is updated
def updateData(DeviceModel):
    global last_print_time
    
    current_time = time.time()
    
    # 1초에 한 번만 출력하도록 제어
    if current_time - last_print_time >= 1.0:
        last_print_time = current_time
        
        try:
            # 주요 센서 데이터 추출
            acc_x = DeviceModel.get("AccX")
            acc_y = DeviceModel.get("AccY")
            ang_x = DeviceModel.get("AngX")
            ang_z = DeviceModel.get("AngZ") # Yaw
            
            print(f"[{time.strftime('%H:%M:%S')}] A:({acc_x:.2f}, {acc_y:.2f}) / Angle(Roll/Yaw): ({ang_x:.2f}, {ang_z:.2f}) deg")
        except AttributeError:
            print(f"Data Update: {DeviceModel.deviceData}")
        except TypeError:
             # 데이터가 아직 초기화되지 않은 경우
             pass


# 스캔 및 연결을 관리하는 메인 비동기 함수
async def main():
    global devices
    
    # 1. 스캔 로직 실행
    print("Bluetooth 장치 스캔 중......")
    try:
        devices = await bleak.BleakScanner.discover(timeout=5.0)
        print("스캔 종료.")
        
        # WitMotion 장치 필터링 및 출력
        target_devices = []
        print("\n--- 검색된 WitMotion 장치 목록 ---")
        for i, d in enumerate(devices):
            if d.name is not None and "WT" in d.name:
                target_devices.append(d)
                print(f"[{i+1}] 이름: {d.name}, 주소: {d.address}")

        if not target_devices:
            print("검색된 WT 장치가 없습니다. 프로그램을 종료합니다.")
            return

    except Exception as ex:
        print("Bluetooth 스캔 시작 실패 또는 오류 발생.")
        print(ex)
        return

    # 2. 장치 선택 로직 (번호 또는 Mac 주소 입력)
    device_to_connect = None
    while True:
        try:
            user_input = d.address#input(
           #     f"연결할 장치 번호(1-{len(target_devices)}) 또는 Mac 주소를 입력하세요: "
            #)
            
            # 번호 입력 시도
            #index = int(user_input) - 1
            index = 0
            if 0 <= index < len(target_devices):
                device_to_connect = target_devices[index]
                break
            
            print("잘못된 번호입니다. Mac 주소 입력을 시도합니다.")

        except ValueError:
            # Mac 주소로 처리0
            for device in target_devices:
                if device.address.lower() == user_input.lower():
                    device_to_connect = device
                    break
            if device_to_connect:
                break
            
            print("일치하는 장치 번호나 Mac 주소를 찾을 수 없습니다. 다시 시도해 주세요.")
            
        except KeyboardInterrupt:
            print("\n사용자 요청으로 프로그램 종료.")
            return

    # 3. 장치 연결 및 데이터 수신 시작
    if device_to_connect:
        device = DeviceModel(
            device_to_connect.name, 
            device_to_connect.address, 
            updateData
        )
        
        # openDevice 함수 실행 (연결 루프를 비동기로 시작)
        await device.openDevice()
        
    else:
        print("연결할 장치가 선택되지 않았습니다. 프로그램 종료.")


if __name__ == '__main__':
    try:
        # 단일 비동기 루프 실행
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n사용자 요청으로 프로그램이 안전하게 종료됩니다.")
    except Exception as e:
        print(f"\n프로그램 실행 중 치명적인 오류 발생: {e}")
