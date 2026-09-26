<#
Copies the goblins into a Unity project, under Assets/Goblins (the layout MedievalSetting uses):
  unity/Goblins/Runtime, Editor              -> Assets/Goblins/Scripts/Runtime, Editor
  export/Goblin.fbx, export/Props, export/Anims -> Assets/Goblins/Models, Models/Props, Models/Anims
  textures/T_Goblin_*.png                     -> Assets/Goblins/Textures
Files are overwritten in place; their .meta files (import settings, prefab references) are kept.
Afterwards, in Unity: Tools > Goblins > Rebuild Prefabs and Showcase (it runs by itself the first time).

Usage:
  powershell -ExecutionPolicy Bypass -File tools\install_to_unity.ps1 -Project E:\Unity\Projects\MedievalSetting
  add -ScriptsOnly to copy only the C# scripts
#>
param(
    [Parameter(Mandatory = $true)][string]$Project,
    [switch]$ScriptsOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$Project = (Resolve-Path $Project).Path
$assets = Join-Path $Project 'Assets'
if (-not (Test-Path $assets)) { throw "No Assets folder in $Project - is it a Unity project?" }
$dst = Join-Path $assets 'Goblins'

function Copy-Into([string]$from, [string]$filter, [string]$to) {
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    $files = @(Get-ChildItem -Path $from -Filter $filter -File)
    foreach ($f in $files) { Copy-Item -LiteralPath $f.FullName -Destination $to -Force }
    Write-Host ("{0,3} x {1,-16} -> {2}" -f $files.Count, $filter, $to.Substring($Project.Length + 1))
}

Copy-Into (Join-Path $root 'unity\Goblins\Runtime') '*.cs' (Join-Path $dst 'Scripts\Runtime')
Copy-Into (Join-Path $root 'unity\Goblins\Editor') '*.cs' (Join-Path $dst 'Scripts\Editor')
if (-not $ScriptsOnly) {
    Copy-Into (Join-Path $root 'export') 'Goblin.fbx' (Join-Path $dst 'Models')
    Copy-Into (Join-Path $root 'export\Props') '*.fbx' (Join-Path $dst 'Models\Props')
    Copy-Into (Join-Path $root 'export\Anims') '*.fbx' (Join-Path $dst 'Models\Anims')
    Copy-Into (Join-Path $root 'textures') 'T_Goblin_*.png' (Join-Path $dst 'Textures')
}
Write-Host 'Done. In Unity: Tools > Goblins > Rebuild Prefabs and Showcase'
