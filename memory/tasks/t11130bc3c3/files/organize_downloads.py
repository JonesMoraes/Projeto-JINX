#!/usr/bin/env python3
"""
Downloads Folder Organizer
Automated script to organize files in the Downloads directory into category subfolders.
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

# Mapping of folder names to sets of file extensions (lowercase, with dot)
CATEGORY_MAPPING = {
    "Documents": {
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", 
        ".md", ".tex", ".epub", ".mobi", ".djvu"
    },
    "Spreadsheets": {
        ".xls", ".xlsx", ".csv", ".ods", ".numbers", ".tsv"
    },
    "Presentations": {
        ".ppt", ".pptx", ".key", ".odp"
    },
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", 
        ".tiff", ".tif", ".heic", ".ico", ".raw", ".psd", ".ai", ".eps"
    },
    "Audio": {
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", 
        ".mid", ".midi", ".alac", ".aiff"
    },
    "Videos": {
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", 
        ".m4v", ".3gp", ".mpeg", ".mpg"
    },
    "Archives": {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", 
        ".tgz", ".iso", ".cab"
    },
    "Installers & Executables": {
        ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage"
    },
    "Code & Data": {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", 
        ".xml", ".sql", ".java", ".cpp", ".c", ".h", ".cs", ".php", 
        ".sh", ".bat", ".ps1", ".yaml", ".yml", ".rb", ".go", ".rs"
    },
    "Design & 3D": {
        ".stl", ".obj", ".blend", ".step", ".stp", ".dwg", ".dxf", ".fbx"
    },
    "Fonts": {
        ".ttf", ".otf", ".woff", ".woff2"
    }
}

# Temporary / incomplete download extensions to skip by default
SKIP_EXTENSIONS = {".crdownload", ".tmp", ".part", ".download"}

def get_category(file_ext):
    ext = file_ext.lower()
    if ext in SKIP_EXTENSIONS:
        return None
    for category, extensions in CATEGORY_MAPPING.items():
        if ext in extensions:
            return category
    return "Other Files"

def get_unique_path(destination_dir, filename):
    base_name, extension = os.path.splitext(filename)
    counter = 1
    target_path = destination_dir / filename
    while target_path.exists():
        target_path = destination_dir / f"{base_name}_{counter}{extension}"
        counter += 1
    return target_path

def organize_downloads(target_dir, dry_run=False, include_others=True):
    target_path = Path(target_dir).resolve()
    if not target_path.exists() or not target_path.is_dir():
        print(f"Error: Directory '{target_path}' does not exist.")
        return

    category_folders = set(CATEGORY_MAPPING.keys()) | {"Other Files"}

    print(f"Organizing files in: {target_path}")
    if dry_run:
        print("=== DRY RUN MODE (No files will be moved) ===")

    stats = {cat: 0 for cat in category_folders}
    skipped_count = 0

    items = list(target_path.iterdir())
    for item in items:
        # Ignore subdirectories (including existing category folders)
        if item.is_dir():
            continue
        
        # Ignore hidden system files like .DS_Store
        if item.name.startswith("."):
            continue

        ext = item.suffix
        category = get_category(ext)

        if category is None:
            # Temporary download file
            print(f"Skipping temporary download file: {item.name}")
            skipped_count += 1
            continue

        if category == "Other Files" and not include_others:
            skipped_count += 1
            continue

        dest_dir = target_path / category
        dest_file = get_unique_path(dest_dir, item.name)

        stats[category] += 1

        if dry_run:
            print(f"[DRY-RUN] Would move: '{item.name}' -> '{category}/{dest_file.name}'")
        else:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(dest_file))
            print(f"Moved: '{item.name}' -> '{category}/{dest_file.name}'")

    print("\n" + "="*40)
    print("ORGANIZATION SUMMARY:")
    print("="*40)
    total_moved = 0
    for cat, count in sorted(stats.items()):
        if count > 0:
            print(f"  {cat}: {count} file(s)")
            total_moved += count
    print(f"  Skipped / Ignored: {skipped_count} file(s)")
    print(f"Total files organized: {total_moved}")
    print("="*40)

if __name__ == "__main__":
    default_downloads = Path.home() / "Downloads"
    parser = argparse.ArgumentParser(description="Organize Downloads folder into categorized subfolders.")
    parser.add_argument("--path", type=str, default=str(default_downloads), help="Path to Downloads directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate organization without moving files")
    parser.add_argument("--skip-others", action="store_true", help="Do not move uncategorized files into 'Other Files'")

    args = parser.parse_args()
    organize_downloads(args.path, dry_run=args.dry_run, include_others=not args.skip_others)
