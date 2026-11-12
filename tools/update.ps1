# SC-Dash Update: holt die neueste Version von GitHub (wird von update.bat aufgerufen).
#   -Dir   Programmordner von SC-Dash
#   -Zip   (nur für Tests) lokales Archiv statt Download
param(
    [Parameter(Mandatory = $true)][string]$Dir,
    [string]$Zip = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # macht Downloads in Windows PowerShell 5.1 viel schneller
$Repo = "Phantom-35/StarCitizen-Dash"

function Get-Version([string]$Folder) {
    $file = Join-Path $Folder "scdash\__init__.py"
    if (-not (Test-Path $file)) { return $null }
    $m = [regex]::Match((Get-Content $file -Raw), '__version__\s*=\s*"([0-9.]+)"')
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}

try {
    $Dir = (Resolve-Path $Dir).Path
    $installed = Get-Version $Dir
    if (-not $installed) { throw "In $Dir ist kein SC-Dash (scdash\__init__.py fehlt)." }
    Write-Host ""
    Write-Host "  SC-Dash Update"
    Write-Host "  Installiert: $installed   Ordner: $Dir"

    # Mit git geholt? Dann einfach git pull.
    if (-not $Zip -and (Test-Path (Join-Path $Dir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "  git-Ordner erkannt: hole die neueste Version mit git pull ..."
        git -C $Dir pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw "git pull hat nicht geklappt (lokale Änderungen?). Bitte von Hand prüfen." }
        Write-Host "  Fertig. Jetzt: $(Get-Version $Dir). SC-Dash neu starten."
        exit 0
    }

    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("scdash-update-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        if (-not $Zip) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $headers = @{ "User-Agent" = "SC-Dash-Updater"; "Accept" = "application/vnd.github+json" }
            $rel = Invoke-RestMethod -UseBasicParsing -Headers $headers "https://api.github.com/repos/$Repo/releases/latest"
            $latest = ([string]$rel.tag_name).TrimStart("v")
            Write-Host "  Neueste Version auf GitHub: $latest"
            if ([version]$latest -le [version]$installed) {
                Write-Host "  Du hast schon die neueste Version."
                exit 0
            }
            $Zip = Join-Path $tmp "scdash.zip"
            Write-Host "  Lade herunter ..."
            Invoke-WebRequest -UseBasicParsing -Headers $headers -OutFile $Zip "https://github.com/$Repo/archive/refs/tags/$($rel.tag_name).zip"
        }
        $out = Join-Path $tmp "x"
        Expand-Archive -Path $Zip -DestinationPath $out -Force
        $src = Get-ChildItem $out -Directory | Select-Object -First 1
        if (-not $src -or -not (Get-Version $src.FullName)) { throw "Das Archiv enthält kein SC-Dash." }
        $new = Get-Version $src.FullName
        Write-Host "  Installiere $new ..."
        Copy-Item -Path (Join-Path $src.FullName "*") -Destination $Dir -Recurse -Force
        Write-Host "  Fertig: SC-Dash $new. Läuft das Dashboard gerade, bitte einmal schließen und neu starten."
    }
    finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "  Update fehlgeschlagen: $($_.Exception.Message)"
    Write-Host "  Alternativ: https://github.com/$Repo/releases/latest  (ZIP laden und entpacken)"
    exit 1
}
