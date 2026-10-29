# audio_endpoint.ps1 - hide/show a Windows audio endpoint (same as Sound settings: Disable / Enable) and set the default one. Needs an elevated shell.
#   powershell -File tools\audio_endpoint.ps1 -Cmd list                                     (all capture and render endpoints that exist, with state)
#   powershell -File tools\audio_endpoint.ps1 -Cmd hide   -Id '{0.0.1.00000000}.{guid}'     (disable the endpoint)
#   powershell -File tools\audio_endpoint.ps1 -Cmd show   -Id '{0.0.1.00000000}.{guid}'     (enable it again)
#   powershell -File tools\audio_endpoint.ps1 -Cmd default -Id '{...}' -Role 0|1|2           (0 console, 1 multimedia, 2 communications)
param([string]$Cmd = 'list', [string]$Id = '', [int]$Role = 2, [int]$Seconds = 60, [string]$Match = 'Bose')
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
[ComImport, Guid("F8679F50-850A-41CF-9C72-430F290290C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPolicyConfig {
  int GetMixFormat(IntPtr a, IntPtr b); int GetDeviceFormat(IntPtr a, int b, IntPtr c); int ResetDeviceFormat(IntPtr a); int SetDeviceFormat(IntPtr a, IntPtr b, IntPtr c);
  int GetProcessingPeriod(IntPtr a, int b, IntPtr c, IntPtr d); int SetProcessingPeriod(IntPtr a, IntPtr b); int GetShareMode(IntPtr a, IntPtr b); int SetShareMode(IntPtr a, IntPtr b);
  int GetPropertyValue(IntPtr a, IntPtr b, IntPtr c); int SetPropertyValue(IntPtr a, IntPtr b, IntPtr c);
  int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, int role);
  int SetEndpointVisibility([MarshalAs(UnmanagedType.LPWStr)] string id, int visible);
}
[ComImport, Guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")] public class PolicyConfigClient {}
public static class PC {
  public static int Visible(string id, bool v) { return ((IPolicyConfig)new PolicyConfigClient()).SetEndpointVisibility(id, v ? 1 : 0); }
  public static int Default(string id, int role) { return ((IPolicyConfig)new PolicyConfigClient()).SetDefaultEndpoint(id, role); }
}
'@
switch ($Cmd) {
  'list' {
    foreach ($flow in 'Capture','Render') {
      Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\$flow" | ForEach-Object {
        $st = (Get-ItemProperty $_.PSPath).DeviceState
        if ($st -eq 1 -or $st -eq 2) {   # 1 active, 2 disabled
          $p = Get-ItemProperty "$($_.PSPath)\Properties" -ErrorAction SilentlyContinue
          "{0} {1} state={2} {3} / {4}" -f $flow, $_.PSChildName, $st, $p.'{a45c254e-df1c-4efd-8020-67d146a850e0},2', $p.'{b3f8fa53-0004-438e-9003-51a46e139bfc},6' } } } }
  'watch' {
    $end = (Get-Date).AddSeconds($Seconds); $done = @{}
    while ((Get-Date) -lt $end) {
      Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture' | ForEach-Object {
        $k = $_.PSChildName
        if (-not $done.ContainsKey($k) -and (Get-ItemProperty $_.PSPath).DeviceState -eq 1) {
          $p = Get-ItemProperty "$($_.PSPath)\Properties" -ErrorAction SilentlyContinue
          $name = [string]$p.'{a45c254e-df1c-4efd-8020-67d146a850e0},2' + ' / ' + [string]$p.'{b3f8fa53-0004-438e-9003-51a46e139bfc},6'
          if ($name -match $Match) { $r = [PC]::Visible('{0.0.1.00000000}.' + $k, $false); $done[$k] = 1; (Get-Date).ToString('HH:mm:ss.fff') + ' hid ' + $k + ' ' + $name + ' -> 0x' + $r.ToString('X') } } }
      Start-Sleep -Milliseconds 100 } }
  'hide'    { $r = [PC]::Visible($Id, $false); "hide " + $Id + " -> 0x" + $r.ToString('X') }
  'show'    { $r = [PC]::Visible($Id, $true);  "show " + $Id + " -> 0x" + $r.ToString('X') }
  'default' { $r = [PC]::Default($Id, $Role);  "default(" + $Role + ") " + $Id + " -> 0x" + $r.ToString('X') }
}
