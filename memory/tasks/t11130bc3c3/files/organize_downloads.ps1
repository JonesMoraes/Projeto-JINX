<#
.SYNOPSIS
    Organizes the Downloads folder into categorized subdirectories.
.DESCRIPTION
    Scans the Downloads folder (or specified path) and moves files into organized
    subfolders based on extension, preserving existing folders and avoiding overwriting.
.PARAMETER Path
    Target directory path. Defaults to $HOME\Downloads.
.PARAMETER WhatIf
    Simulate the organization without moving files.
#>

[CmdletBinding(SupportsShouldProcess=$true)]
param (
    [string]$TargetFolder = "$HOME\Downloads",
    [switch]$WhatIfMode = $false
)

if (-not (Test-Path -Path $TargetFolder)) {
    Write-Error "Folder '$TargetFolder' does not exist."
    return
}

# Category extension dictionary
$Categories = @{
    "Documents"               = @(".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md", ".tex", ".epub", ".mobi")
    "Spreadsheets"            = @(".xls", ".xlsx", ".csv", ".ods", ".numbers", ".tsv")
    "Presentations"           = @(".ppt", ".pptx", ".key", ".odp")
    "Images"                  = @(".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif", ".heic", ".ico", ".raw", ".psd", ".ai")
    "Audio"                   = @(".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".mid", ".midi")
    "Videos"                  = @(".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v", ".3gp")
    "Archives"                = @(".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cab")
    "Installers & Executables"= @(".exe", ".msi", ".pkg", ".deb", ".rpm", ".appimage")
    "Code & Data"             = @(".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".sql", ".java", ".cpp", ".c", ".h", ".cs", ".php", ".ps1", ".bat", ".sh", ".yaml", ".yml")
    "Design & 3D"             = @(".stl", ".obj", ".blend", ".step", ".stp", ".dwg", ".dxf", ".fbx")
    "Fonts"                   = @(".ttf", ".otf", ".woff", ".woff2")
}

$SkipExt = @(".crdownload", ".tmp", ".part", ".download")

Write-Host "Organizing files in: $TargetFolder" -ForegroundColor Cyan
if ($WhatIfMode) {
    Write-Host "=== WHAT-IF MODE (No files will actually be moved) ===" -ForegroundColor Yellow
}

$files = Get-ChildItem -Path $TargetFolder -File -Force | Where-Object { -not $_.Name.StartsWith(".") }
$counts = @{}
$skipped = 0

foreach ($file in $files) {
    $ext = $file.Extension.ToLower()

    if ($SkipExt -contains $ext) {
        Write-Host "Skipping partial download: $($file.Name)" -ForegroundColor DarkGray
        $skipped++
        continue
    }

    $targetCategory = "Other Files"
    foreach ($category in $Categories.Keys) {
        if ($Categories[$category] -contains $ext) {
            $targetCategory = $category
            break
        }
    }

    $categoryDir = Join-Path -Path $TargetFolder -ChildPath $targetCategory

    # Destination filename collision handling
    $targetFilePath = Join-Path -Path $categoryDir -ChildPath $file.Name
    $counter = 1
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
    
    while (Test-Path -Path $targetFilePath) {
        $newFileName = "${baseName}_${counter}${ext}"
        $targetFilePath = Join-Path -Path $categoryDir -ChildPath $newFileName
        $counter++
    }

    if (-not $counts.ContainsKey($targetCategory)) {
        $counts[$targetCategory] = 0
    }
    $counts[$targetCategory]++

    if ($WhatIfMode) {
        Write-Host "[What-If] $($file.Name) -> $targetCategory\$([System.IO.Path]::GetFileName($targetFilePath))" -ForegroundColor Gray
    } else {
        if (-not (Test-Path -Path $categoryDir)) {
            New-Item -ItemType Directory -Path $categoryDir -Force | Out-Null
        }
        Move-Item -Path $file.FullName -Destination $targetFilePath
        Write-Host "Moved: $($file.Name) -> $targetCategory\$([System.IO.Path]::GetFileName($targetFilePath))" -ForegroundColor Green
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ORGANIZATION SUMMARY:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
$totalMoved = 0
foreach ($cat in ($counts.Keys | Sort-Object)) {
    Write-Host "  $cat : $($counts[$cat]) file(s)"
    $totalMoved += $counts[$cat]
}
Write-Host "  Skipped : $skipped file(s)"
Write-Host "Total files processed: $totalMoved"
Write-Host "========================================" -ForegroundColor Cyan
