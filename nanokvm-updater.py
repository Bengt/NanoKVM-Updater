import os
import shutil
import time
import zipfile
import requests
import logging
from pathlib import Path

class FirmwareUpdater:
    def __init__(self):
        self.temporary = Path("/root/nanokvm-cache")
        self.backup_dir = Path("/root/old")
        self.firmware_dir = Path("/kvmapp")
        self.service_name = "S95nanokvm"
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

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

    def service_control(self, action: str):
        """Control the nanokvm service."""
        result = os.system(f"/etc/init.d/{self.service_name} {action}")
        if result != 0:
            self.logger.error(f"Service {action} failed with code {result}")
            raise RuntimeError(f"Service {action} failed")
        self.logger.info(f"Service {action} completed")

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
