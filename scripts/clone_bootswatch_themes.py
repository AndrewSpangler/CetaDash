import os
import requests
from typing import List
BOOTSWATCH_THEMES = [ # For theme-selector in context provider
    "cerulean", "cosmo", "darkly", "flatly",
    "journal", "litera", "lumen", "lux", "materia",
    "minty", "morph", "pulse", "sandstone", "simplex",
    "slate", "spacelab", "superhero", "united", "vapor", "yeti",
    "zephyr"
]
    
def download_file(url:str, destination:os.PathLike) -> None:
    response = requests.get(url)
    if response.status_code == 200:
        with open(destination, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded {url} to {destination}")
    else:
        print(f"Failed to download {url}. Status code: {response.status_code}")

def download_theme(theme:str, target:os.PathLike) -> None:
    url = f"https://bootswatch.com/5/{theme}/bootstrap.min.css"
    download_file(url, os.path.join(target, f"bootswatch.{theme}.min.css"))

def download_themes(themes:List[str], target:str) -> None:
    for t in themes:
        download_theme(t, target)

if __name__ == "__main__":
    scripts_dir = os.path.dirname(__file__)
    target_dir = os.path.join(os.path.dirname(scripts_dir), "src/appsrc/static/css/bootswatch/")
    os.makedirs(target_dir, exist_ok=True)
    download_themes(BOOTSWATCH_THEMES, target_dir)