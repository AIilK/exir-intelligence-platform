# Creates a shortcut in the current user's Startup folder that runs the reports web app
# without a console window (pythonw). Output goes to logs\app.log.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path (Split-Path -Parent (Get-Command python).Source) 'pythonw.exe'
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Reports Viewer (8765).lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = '"' + (Join-Path $here 'app.py') + '"'
$s.WorkingDirectory = $here
$s.Description = 'Reports web app on port 8765'
$s.WindowStyle = 7
$s.Save()
Write-Output "Created: $lnk"
