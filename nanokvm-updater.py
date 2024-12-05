import os
import shutil
import time
import zipfile
import requests
import logging
from pathlib import Path
from subprocess import run, PIPE, STDOUT

class FirmwareUpdater:
    def __init__(self):
        self.temporary = Path("/root/nanokvm-cache")
        self.backup_dir = Path("/root/old")
        self.firmware_dir = Path("/kvmapp")
        self.kvm_dir = self.firmware_dir / "kvm"
        self.etc_kvm_dir = Path("/etc/kvm")
        self.service_name = "S95nanokvm"
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def service_control(self, action: str):
        """Control the nanokvm service."""
        try:
            cmd = f"/etc/init.d/{self.service_name} {action}"
            result = run(cmd, shell=True, stdout=PIPE, stderr=STDOUT, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Service {action} failed with code {result.returncode}: {result.stdout}")
                raise RuntimeError(f"Service {action} failed")
            
            self.logger.info(f"Service {action} completed")
        except Exception as e:
            self.logger.error(f"Service control failed for action '{action}': {e}")
            raise

    def safe_mkdir(self, path: Path):
        """Create directory if it doesn't exist, ignore if it does."""
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.warning(f"Directory creation warning for {path}: {e}")

    def safe_remove(self, path: Path):
        """Safely remove file or directory if it exists."""
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        except Exception as e:
            self.logger.warning(f"Removal warning for {path}: {e}")

    def safe_execute(self, cmd: str) -> bool:
        """Safely execute a shell command."""
        try:
            result = run(cmd, shell=True, stdout=PIPE, stderr=STDOUT, text=True)
            if result.returncode != 0 and result.stdout and "File exists" not in result.stdout:
                self.logger.warning(f"Command '{cmd}' returned: {result.stdout}")
            return result.returncode == 0
        except Exception as e:
            self.logger.warning(f"Command execution warning for '{cmd}': {e}")
            return False

    def mkdir(self):
        """Create or recreate temporary directory."""
        if self.temporary.exists():
            shutil.rmtree(self.temporary)
        self.temporary.mkdir(exist_ok=True)
        self.logger.info(f"Created temporary directory {self.temporary}")

    def read_file(self, file_path: Path) -> str:
        """Read file content, stripping newlines."""
        try:
            return file_path.read_text().strip()
        except Exception as e:
            self.logger.error(f"Failed to read file {file_path}: {e}")
            raise

    def download_firmware(self):
        """Download and extract the latest firmware."""
        self.logger.info("Downloading firmware...")
        url = f"https://cdn.sipeed.com/nanokvm/latest.zip?n={int(time.time())}"
        zip_file = self.temporary / "latest.zip"
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            if response.headers.get("content-type") != "application/zip":
                raise ValueError(f"Invalid content type: {response.headers.get('content-type')}")
            
            with zip_file.open('wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            with zipfile.ZipFile(zip_file) as zf:
                zf.extractall(self.temporary)
            
            self.logger.info("Firmware download complete")
        except Exception as e:
            self.logger.error(f"Firmware download failed: {e}")
            raise

    def download_lib(self):
        """Download and install library file."""
        self.logger.info("Downloading library...")
        try:
            device_key = self.read_file(Path("/device_key"))
            url = f"https://maixvision.sipeed.com/api/v1/nanokvm/encryption?uid={device_key}"
            headers = {"token": "MaixVision2024"}
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            if response.headers.get("content-type") != "application/octet-stream":
                raise ValueError(f"Invalid content type: {response.headers.get('content-type')}")
            
            lib_file = self.temporary / "libmaixcam_lib.so"
            lib_file.write_bytes(response.content)
            
            lib_dir = self.temporary / "latest/kvm_system/dl_lib"
            shutil.copy(lib_file, lib_dir)
            self.logger.info("Library download complete")
        except Exception as e:
            self.logger.error(f"Library download failed: {e}")
            raise

    def update_firmware(self):
        """Update firmware files with backup."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
        
        if self.firmware_dir.exists():
            shutil.move(str(self.firmware_dir), str(self.backup_dir))
        
        shutil.move(str(self.temporary / "latest"), str(self.firmware_dir))

    def set_permissions(self):
        """Set correct permissions on installed files."""
        for root, dirs, files in os.walk(self.firmware_dir):
            os.chmod(root, 0o755)
            for file in files:
                os.chmod(os.path.join(root, file), 0o755)
        self.logger.info("Permissions updated")

    def setup_directories(self):
        """Setup required directories."""
        self.safe_mkdir(self.kvm_dir)
        self.safe_mkdir(self.etc_kvm_dir)
        
    def cleanup_files(self):
        """Clean up temporary files and directories."""
        paths_to_clean = [
            Path("/tmp/kvm_system"),
            Path("/tmp/server"),
            Path("/etc/init.d/S02udisk"),
            Path("/etc/init.d/S30wifi"),
            self.firmware_dir / "kvm_system/kvm_stream"
        ]
        
        for path in paths_to_clean:
            self.safe_remove(path)

    def handle_kernel_modules(self):
        """Handle kernel module operations."""
        # Attempt to remove modules if loaded
        self.safe_execute("rmmod i2c_gpio 2>/dev/null || true")
        self.safe_execute("rmmod i2c_algo_bit 2>/dev/null || true")
        
        # Insert modules, ignoring if they already exist
        self.safe_execute("insmod /mnt/system/ko/i2c-algo-bit.ko 2>/dev/null || true")
        self.safe_execute("insmod /mnt/system/ko/i2c-gpio.ko 2>/dev/null || true")

    def update(self):
        """Perform complete firmware update process."""
        try:
            self.logger.info("Starting firmware update process...")
            self.service_control("stop")
            
            self.mkdir()
            self.download_firmware()
            self.download_lib()
            self.update_firmware()
            self.set_permissions()
            
            # Additional setup and cleanup
            self.setup_directories()
            self.cleanup_files()
            self.handle_kernel_modules()
            
            version = self.read_file(self.firmware_dir / "version")
            self.logger.info(f"Update to version {version} successful")
            self.logger.info("Restarting service...")
            
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            raise
        finally:
            if self.temporary.exists():
                shutil.rmtree(self.temporary)
            self.service_control("restart")
            
            # Final cleanup of processes
            self.safe_execute("killall NanoKVM-Server 2>/dev/null || true")
            self.cleanup_files()

def main():
    updater = FirmwareUpdater()
    try:
        updater.update()
    except Exception as e:
        logging.error(f"Update process failed: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
