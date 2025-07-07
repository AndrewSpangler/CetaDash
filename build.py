"""
Build.py Copyright Andrew Spangler 2024
Licensed under WTFPL 
Packages up a folder into a zip for distributon
"""
import os
import zipfile

IGNORE_LIST = [".pyc", ".pyd", ".sqlite", ".json"]

def should_ignore(path, ignore_folders: list) -> bool:
    ignore_list = ignore_folders + IGNORE_LIST
    for folder in ignore_list:
        if path.endswith(os.path.normpath(folder)):
            print(f"Ignoring {path}")
            return True
    return False

def zip_directory(source_dir, output_zip, ignore_folders=None) -> None:
    if ignore_folders is None:
        ignore_folders = []
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for entry in os.scandir(source_dir):
            if should_ignore(entry.path, ignore_folders):
                continue
            clean_name = entry.name.replace('\x00', '_')
            if entry.is_file():
                print("FILE -", clean_name)
                zipf.write(entry.path, arcname=clean_name)
            elif entry.is_dir():
                print("DIR -", clean_name)
                if clean_name not in ignore_folders:
                    zip_subdirectory(zipf, entry.path, clean_name, ignore_folders)

def zip_subdirectory(zipf, path, arcname, ignore_folders) -> None:
    for entry in os.scandir(path):
        if should_ignore(entry.path, ignore_folders):
            continue
        clean_name = entry.name.replace('\x00', '_')
        full_arcname = os.path.join(arcname, clean_name)
        if entry.is_file():
            print("FILE -", clean_name)
            zipf.write(entry.path, arcname=full_arcname)
        elif entry.is_dir():
            print("DIR -", clean_name)
            if clean_name not in ignore_folders:
                zip_subdirectory(zipf, entry.path, full_arcname, ignore_folders)

if __name__ == "__main__":
    with open(os.path.join(os.path.dirname(__file__), "src/appsrc/version.py")) as f:
        version = f.read().split("=")[-1].strip().replace('"',"")
    package = os.path.basename(os.path.normpath(os.path.dirname(__file__)))+"-V"+version
    package = os.path.join(os.path.dirname(os.path.dirname(__file__)), package)
    print(f"Packaging to {package}")
    outfile = f"{package}.zip"
    if os.path.isfile(outfile):
        print(f"Removing previous bundle with same version")
        os.remove(outfile)
    zip_directory(
        source:=os.path.dirname(__file__),
        output_zip=outfile,
        ignore_folders=[
            "__pycache__",
            ".vscode",
            ".git",
            ".log"
        ]
    )
    print(f"Directory '{source}' has been zipped to '{os.path.abspath(outfile)}'.")
