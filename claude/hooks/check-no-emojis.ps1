#!/usr/bin/env pwsh
# PostToolUse hook: warn when emojis appear in source files after Edit/Write.
# The project rule is "no emojis in code, comments, documentation, or commits."
# This hook is advisory (non-blocking) — it surfaces violations to the assistant
# so they can be removed before commit.

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
    if (-not $file_path) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    # Only check text source files we care about
    $checked = @('.py', '.ts', '.tsx', '.astro', '.mdx', '.md', '.yaml', '.yml',
                 '.json', '.html', '.css', '.txt', '.tex', '.jinja')
    $ext = [System.IO.Path]::GetExtension($file_path).ToLower()
    if ($ext -notin $checked) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    # Skip third-party / generated trees
    $skip_dirs = @('node_modules', '.cache', 'dist', 'build', '.git',
                   '__pycache__', '.venv', 'output')
    foreach ($d in $skip_dirs) {
        if ($file_path -match [regex]::Escape("\$d\") -or $file_path -match [regex]::Escape("/$d/")) {
            $output | ConvertTo-Json -Compress
            exit 0
        }
    }

    if (-not (Test-Path $file_path)) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    $content = Get-Content $file_path -Raw -Encoding UTF8
    if (-not $content) {
        $output | ConvertTo-Json -Compress
        exit 0
    }

    # Emoji-bearing Unicode ranges (covers most pictographs, emoticons, symbols)
    $emoji_regex = '[\u{1F300}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F1FF}\u{1F200}-\u{1F2FF}\u{1FA70}-\u{1FAFF}]'

    $matches = [regex]::Matches($content, $emoji_regex)
    if ($matches.Count -gt 0) {
        Write-Host "[no-emojis] $($matches.Count) emoji(s) found in $file_path"
        Write-Host "[no-emojis] Project rule: no emojis in code, comments, docs, or commits"
        exit 2
    }
} catch {
    # Silently ignore errors to not block operations
}

$output | ConvertTo-Json -Compress
exit 0
