import shutil
from pathlib import Path


target_dir = Path("test_folder")

fileOrganization = {
    # Documents
    ".pdf": "Documents", 
    ".docx": "Documents", 
    ".doc": "Documents",
    # Images 
    ".png": "Pictures", 
    ".jpg": "Pictures", 
    ".gif": "Pictures",
    # Videos 
    ".mp4": "Videos", 
    ".ogg": "Videos",
    # Musics 
    ".mp3": "Musics", 
    ".wav": "Musics",
    # Archives 
    ".rar": "Archives", 
    ".zip": "Archives"
    }

target_paths = set(fileOrganization.values())

for target_path in target_paths:
    target_creation = target_dir / target_path
    target_creation.mkdir(exist_ok=True)
    print("Created Folder: ", target_creation)

for item in target_dir.iterdir():
    if item.is_file():
        file_path = target_dir / fileOrganization[item.suffix.lower()] / item.name
        counter = 1
        while counter:
            if file_path.exists():
                new_name = item.stem + "_" + str(counter) + item.suffix
                file_path = target_dir / fileOrganization[item.suffix.lower()] / new_name
                counter += 1
            else:
                shutil.move(item, file_path)
                break
    else:
        print(item.name, "/...")