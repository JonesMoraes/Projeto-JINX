#!/usr/bin/env bash

# Downloads Folder Organizer for Bash (macOS & Linux)
TARGET_DIR="${1:-$HOME/Downloads}"
DRY_RUN=0

if [ "$2" == "--dry-run" ] || [ "$1" == "--dry-run" ]; then
    DRY_RUN=1
    if [ "$1" == "--dry-run" ]; then TARGET_DIR="$HOME/Downloads"; fi
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' does not exist."
    exit 1
fi

echo "Organizing files in: $TARGET_DIR"
if [ $DRY_RUN -eq 1 ]; then
    echo "=== DRY RUN MODE (No files will be moved) ==="
fi

# Define categories and extensions
declare -A CATEGORIES
CATEGORIES["Documents"]="pdf doc docx txt rtf odt pages md tex epub mobi"
CATEGORIES["Spreadsheets"]="xls xlsx csv ods numbers tsv"
CATEGORIES["Presentations"]="ppt pptx key odp"
CATEGORIES["Images"]="jpg jpeg png gif bmp svg webp tiff tif heic ico raw psd ai"
CATEGORIES["Audio"]="mp3 wav flac aac ogg m4a wma mid midi"
CATEGORIES["Videos"]="mp4 mkv mov avi webm wmv flv m4v 3gp"
CATEGORIES["Archives"]="zip rar 7z tar gz bz2 xz iso cab tgz"
CATEGORIES["Installers_Executables"]="exe msi dmg pkg deb rpm appimage"
CATEGORIES["Code_Data"]="py js ts html css json xml sql java cpp c h cs php sh bat ps1 yaml yml"
CATEGORIES["Design_3D"]="stl obj blend step stp dwg dxf fbx"
CATEGORIES["Fonts"]="ttf otf woff woff2"

# Move files
cd "$TARGET_DIR" || exit 1

for file in *; do
    # Skip directories and hidden files
    [ -f "$file" ] || continue
    [[ "$file" == .* ]] && continue

    ext="${file##*.}"
    ext_lower="$(echo "$ext" | tr '[:upper:]' '[:lower:]')"

    # Skip partial downloads
    if [[ "$ext_lower" == "crdownload" || "$ext_lower" == "tmp" || "$ext_lower" == "part" || "$ext_lower" == "download" ]]; then
        echo "Skipping partial download: $file"
        continue
    fi

    target_cat="Other_Files"
    for cat in "${!CATEGORIES[@]}"; do
        for e in ${CATEGORIES[$cat]}; do
            if [ "$ext_lower" == "$e" ]; then
                target_cat="$cat"
                break 2
            fi
        done
    done

    dest_folder="$TARGET_DIR/$target_cat"
    dest_path="$dest_folder/$file"

    # Collision avoidance
    if [ -e "$dest_path" ]; then
        filename="${file%.*}"
        extension="${file##*.}"
        counter=1
        while [ -e "$dest_folder/${filename}_${counter}.${extension}" ]; do
            ((counter++))
        done
        dest_path="$dest_folder/${filename}_${counter}.${extension}"
    fi

    if [ $DRY_RUN -eq 1 ]; then
        echo "[DRY-RUN] Would move: '$file' -> '$target_cat/$(basename "$dest_path")'"
    else
        mkdir -p "$dest_folder"
        mv "$file" "$dest_path"
        echo "Moved: '$file' -> '$target_cat/$(basename "$dest_path")'"
    fi
done

echo ""
echo "Organization Complete!"
