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

    # ... (rest of the previous methods remain the same)

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
