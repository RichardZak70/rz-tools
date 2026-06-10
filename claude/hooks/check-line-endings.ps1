#!/usr/bin/env pwsh
# PostToolUse hook: normalize line endings after Edit/Write.
# - LF for text source files
# - CRLF for Windows-specific files (.ps1, .bat, .cmd)

$ErrorActionPreference = "SilentlyContinue"

$input_json = [Console]::In.ReadToEnd()

$output = @{
    continue = $true
    stopReason = $null
}

try {
    $data = $input_json | ConvertFrom-Json
    $tool_name = $data.tool_name
    if ($tool_name -notin @("Write", "Edit")) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    $file_path = $data.tool_input.file_path
    if (-not $file_path -or -not (Test-Path $file_path)) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    $ext = [System.IO.Path]::GetExtension($file_path).ToLower()
    $crlf_extensions = @('.ps1', '.bat', '.cmd')
    $lf_extensions = @('.py', '.ts', '.tsx', '.astro', '.mdx', '.md',
                       '.yaml', '.yml', '.json', '.html', '.css', '.txt',
                       '.tex', '.jinja', '.toml', '.xml', '.svg', '.sh')

    $all_checked = $crlf_extensions + $lf_extensions
    if ($ext -notin $all_checked) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    # Skip third-party trees
    $skip_dirs = @('node_modules', '.cache', 'dist', 'build', '.git',
                   '__pycache__', '.venv', 'output')
    foreach ($d in $skip_dirs) {
        if ($file_path -match [regex]::Escape("\$d\") -or $file_path -match [regex]::Escape("/$d/")) {
            $output | ConvertTo-Json -Compress
            exit 0
        }
    }

    $raw = [System.IO.File]::ReadAllBytes($file_path)
    if ($raw.Length -eq 0) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    $text = [System.Text.Encoding]::UTF8.GetString($raw)
    $expect_crlf = $ext -in $crlf_extensions

    if ($expect_crlf) {
        $normalized = $text -replace "`r`n", "`n" -replace "`r", "`n"
        $fixed = $normalized -replace "`n", "`r`n"
    } else {
        $fixed = $text -replace "`r`n", "`n" -replace "`r", "`n"
    }

    if ($fixed -ne $text) {
        $target = if ($expect_crlf) { "CRLF" } else { "LF" }
        [System.IO.File]::WriteAllText(
            $file_path,
            $fixed,
            (New-Object System.Text.UTF8Encoding($false))
        )
        Write-Host "[line-endings] Normalized to $target -> $file_path"
        exit 2
    }
} catch {
    # Silently ignore errors to not block operations
}

$output | ConvertTo-Json -Compress
exit 0
