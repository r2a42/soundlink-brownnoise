# media_key.ps1 - send a global media key (what a keyboard's play/pause key does); Chrome and Windows route it to the active media session.
#   powershell -File tools\media_key.ps1 -Key playpause|next|prev|stop|volup|voldown|mute
param([Parameter(Mandatory=$true)][string]$Key)
Add-Type -Namespace K -Name N -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);'
$vk = @{ playpause = 0xB3; stop = 0xB2; next = 0xB0; prev = 0xB1; volup = 0xAF; voldown = 0xAE; mute = 0xAD }[$Key]
if (-not $vk) { throw "unknown key $Key" }
[K.N]::keybd_event([byte]$vk, 0, 0, [UIntPtr]::Zero)       # key down
[K.N]::keybd_event([byte]$vk, 0, 2, [UIntPtr]::Zero)       # key up (KEYEVENTF_KEYUP)
Write-Output ("{0} sent {1}" -f (Get-Date).ToString('HH:mm:ss.fff'), $Key)
