param([Parameter(Mandatory=$true)][string]$Addr, [switch]$NoDisable, [switch]$DisconnectOnly)   # -NoDisable: only enable (the disable step tears down the Windows audio endpoint and stalls capture)  # speaker Bluetooth address, 12 hex digits, no colons
# Windows PowerShell 5.1. Enable (connect) the audio profiles of the paired speaker, as the Windows Connect button does.
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class Bth {
  [DllImport("bthprops.cpl", SetLastError=true)] public static extern uint BluetoothGetDeviceInfo(IntPtr hRadio, IntPtr info);
  [DllImport("bthprops.cpl", SetLastError=true)] public static extern uint BluetoothSetServiceState(IntPtr hRadio, IntPtr info, ref Guid svc, uint flags);
}
'@
$buf = [Runtime.InteropServices.Marshal]::AllocHGlobal(560)
for ($i=0; $i -lt 560; $i++) { [Runtime.InteropServices.Marshal]::WriteByte($buf, $i, 0) }
[Runtime.InteropServices.Marshal]::WriteInt32($buf, 0, 560)
[Runtime.InteropServices.Marshal]::WriteInt64($buf, 8, [Convert]::ToInt64($Addr, 16))
$r = [Bth]::BluetoothGetDeviceInfo([IntPtr]::Zero, $buf)
Write-Output ("{0} GetDeviceInfo={1} connected={2} remembered={3}" -f (Get-Date).ToString('HH:mm:ss.fff'), $r, [Runtime.InteropServices.Marshal]::ReadInt32($buf, 20), [Runtime.InteropServices.Marshal]::ReadInt32($buf, 24))
if ($r -ne 0) { exit 1 }
foreach ($g in '0000110b-0000-1000-8000-00805f9b34fb','0000111e-0000-1000-8000-00805f9b34fb') {
  $guid = [Guid]$g
  $d = 'skipped'
  if ($DisconnectOnly) { $d = [Bth]::BluetoothSetServiceState([IntPtr]::Zero, $buf, [ref]$guid, 0); Write-Output ('{0} {1} disable={2} (disconnect only)' -f (Get-Date).ToString('HH:mm:ss.fff'), $g, $d); continue }
  if (-not $NoDisable) { $d = [Bth]::BluetoothSetServiceState([IntPtr]::Zero, $buf, [ref]$guid, 0); Start-Sleep -Milliseconds 500 }
  $e = [Bth]::BluetoothSetServiceState([IntPtr]::Zero, $buf, [ref]$guid, 1)
  Write-Output ("{0} {1} disable={2} enable={3}" -f (Get-Date).ToString('HH:mm:ss.fff'), $g, $d, $e)
}
Start-Sleep -Seconds 3
$r = [Bth]::BluetoothGetDeviceInfo([IntPtr]::Zero, $buf)
Write-Output ("{0} after: connected={1}" -f (Get-Date).ToString('HH:mm:ss.fff'), [Runtime.InteropServices.Marshal]::ReadInt32($buf, 20))
