#!/usr/bin/env pwsh
# Markdown linting hook for .claude/*.md files
# Runs after Edit/Write operations on markdown files

$ErrorActionPreference = "SilentlyContinue"

# Read input from stdin
$input_json = [Console]::In.ReadToEnd()

# Initialize output
$output = @{
    continue = $true
    stopReason = $null
}

try {
    $data = $input_json | ConvertFrom-Json

    # Get file path from tool input
    $file_path = $data.tool_input.file_path

    # Only process .claude markdown files
    if ($file_path -and $file_path -match "\.claude.*\.md$") {
        $project_dir = $PWD.Path
        $config_file = Join-Path $project_dir ".markdownlint-claude.json"

        if (Test-Path $config_file) {
            # Run markdownlint with Claude-specific config
            $result = npx markdownlint-cli --config $config_file $file_path 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Markdown lint issues in ${file_path}:"
                Write-Host $result
            }
        }
    }
} catch {
    # Silently ignore errors to not block operations
}

# Output result as JSON (required by Claude Code hooks)
$output | ConvertTo-Json -Compress

exit 0
