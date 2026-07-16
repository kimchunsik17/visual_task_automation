import os
import shutil
import subprocess
import glob
from pathlib import Path

REPO_URL = "https://github.com/enescingoz/awesome-n8n-templates.git"
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp_repo")
TARGET_DIR = os.path.join(os.path.dirname(__file__), "scraped_templates")

def clone_repo():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    print(f"Cloning {REPO_URL} into {TEMP_DIR}...")
    subprocess.run(["git", "clone", REPO_URL, TEMP_DIR], check=True)

def copy_templates():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    print(f"Searching for .json files in {TEMP_DIR}...")
    json_files = glob.glob(os.path.join(TEMP_DIR, "**", "*.json"), recursive=True)
    
    count = 0
    for file_path in json_files:
        # Avoid hidden directories like .git
        if ".git" in file_path:
            continue
            
        # Get relative path to maintain category structure
        rel_path = os.path.relpath(file_path, TEMP_DIR)
        target_path = os.path.join(TARGET_DIR, rel_path)
        
        # Ensure target directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Copy file
        shutil.copy2(file_path, target_path)
        count += 1
        
    print(f"Successfully copied {count} template files to {TARGET_DIR}.")

def cleanup():
    if os.path.exists(TEMP_DIR):
        print(f"Cleaning up {TEMP_DIR}...")
        # on Windows, sometimes rmtree fails due to .git read-only files.
        # we'll use a robust rmtree method or just ignore errors.
        def remove_readonly(func, path, excinfo):
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(TEMP_DIR, onerror=remove_readonly)
        print("Cleanup complete.")

if __name__ == "__main__":
    try:
        clone_repo()
        copy_templates()
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        cleanup()
