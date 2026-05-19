param(
    [ValidateSet("codex", "claude", "opencode", "all")]
    [string]$Target = $(if ($env:TARGET) { $env:TARGET } else { "codex" }),

    [string]$RepoUrl = $(if ($env:CHIP_NETLIST_REPO_URL) { $env:CHIP_NETLIST_REPO_URL } else { "https://github.com/yangzhaoxu411/chip-netlist-skill.git" }),

    [string]$Branch = $(if ($env:CHIP_NETLIST_BRANCH) { $env:CHIP_NETLIST_BRANCH } else { "main" }),

    [string]$Source = $(if ($env:CHIP_NETLIST_SOURCE) { $env:CHIP_NETLIST_SOURCE } else { "" })
)

$ErrorActionPreference = "Stop"
$SkillName = "chip-netlist"

function Get-InstallRoot {
    if ($env:CHIP_NETLIST_INSTALL_ROOT) {
        New-Item -ItemType Directory -Force -Path $env:CHIP_NETLIST_INSTALL_ROOT | Out-Null
        return (Resolve-Path -LiteralPath $env:CHIP_NETLIST_INSTALL_ROOT).Path
    }
    return ""
}

function Get-TargetPath([string]$Name) {
    $homeDir = [Environment]::GetFolderPath("UserProfile")
    $testRoot = Get-InstallRoot
    if ($testRoot) {
        switch ($Name) {
            "codex" { return (Join-Path $testRoot "codex/skills/$SkillName") }
            "claude" { return (Join-Path $testRoot "claude/skills/$SkillName") }
            "opencode" { return (Join-Path $testRoot "opencode/skill/$SkillName") }
        }
    }

    switch ($Name) {
        "codex" { return (Join-Path $homeDir ".codex/skills/$SkillName") }
        "claude" { return (Join-Path $homeDir ".claude/skills/$SkillName") }
        "opencode" { return (Join-Path $homeDir ".config/opencode/skill/$SkillName") }
    }
}

function Resolve-SkillSource {
    if ($Source) {
        $candidate = Join-Path $Source $SkillName
        if (Test-Path -LiteralPath (Join-Path $candidate "SKILL.md")) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        if (Test-Path -LiteralPath (Join-Path $Source "SKILL.md")) {
            return (Resolve-Path -LiteralPath $Source).Path
        }
        throw "Source does not contain $SkillName/SKILL.md or SKILL.md: $Source"
    }

    if ($PSScriptRoot) {
        $localCandidate = Join-Path $PSScriptRoot $SkillName
        if (Test-Path -LiteralPath (Join-Path $localCandidate "SKILL.md")) {
            return (Resolve-Path -LiteralPath $localCandidate).Path
        }
    }
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        throw "git is required for remote installation. Install git or clone the repo manually."
    }

    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ("chip-netlist-skill-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    git clone --depth 1 --branch $Branch $RepoUrl $temp | Out-Null
    $candidate = Join-Path $temp $SkillName
    if (-not (Test-Path -LiteralPath (Join-Path $candidate "SKILL.md"))) {
        throw "Cloned repository does not contain $SkillName/SKILL.md"
    }
    return $candidate
}

function Install-One([string]$Name, [string]$SkillSource) {
    $dest = Get-TargetPath $Name
    $parent = Split-Path -Parent $dest
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $dest) {
        Remove-Item -LiteralPath $dest -Recurse -Force
    }
    Copy-Item -LiteralPath $SkillSource -Destination $dest -Recurse -Force
    Write-Host "Installed $SkillName for $Name -> $dest"
}

$skillSource = Resolve-SkillSource
$targets = if ($Target -eq "all") { @("codex", "claude", "opencode") } else { @($Target) }
foreach ($name in $targets) {
    Install-One $name $skillSource
}

Write-Host "Done. Restart the target agent so it can discover $SkillName."

