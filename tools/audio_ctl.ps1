# audio_ctl.ps1 - read/set Windows endpoint volume and read live peak meters (Core Audio, no installs).
#   powershell -File tools\audio_ctl.ps1 -Cmd list
#   powershell -File tools\audio_ctl.ps1 -Cmd get  -Flow capture|render
#   powershell -File tools\audio_ctl.ps1 -Cmd set  -Flow capture -Level 0.80
#   powershell -File tools\audio_ctl.ps1 -Cmd peak -Flow render -Seconds 5      (peak meter of the default endpoint)
#   powershell -File tools\audio_ctl.ps1 -Cmd sessions                           (render sessions: which app is producing sound)
param([string]$Cmd = 'list', [string]$Flow = 'capture', [double]$Level = -1, [int]$Seconds = 3)
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
namespace CA {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] public class MMDeviceEnumerator {}
  [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IMMDeviceEnumerator { int EnumAudioEndpoints(int f,int m,out IntPtr d); int GetDefaultAudioEndpoint(int f,int r,out IMMDevice d); }
  [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IMMDevice { int Activate(ref Guid iid,int ctx,IntPtr p,[MarshalAs(UnmanagedType.IUnknown)] out object o); int OpenPropertyStore(int a,out IntPtr p); int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id); }
  [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IAudioEndpointVolume { int a(IntPtr n); int b(IntPtr n); int c(out uint n); int SetMasterVolumeLevel(float l,ref Guid g); int SetMasterVolumeLevelScalar(float l,ref Guid g);
    int GetMasterVolumeLevel(out float l); int GetMasterVolumeLevelScalar(out float l); int d(uint c,float l,ref Guid g); int e(uint c,float l,ref Guid g); int f(uint c,out float l); int g(uint c,out float l);
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool m,ref Guid g); int GetMute([MarshalAs(UnmanagedType.Bool)] out bool m); }
  [ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IAudioMeterInformation { int GetPeakValue(out float p); }
  public static class Util {
    static IMMDevice Dev(int flow) { var e=(IMMDeviceEnumerator)new MMDeviceEnumerator(); IMMDevice d; e.GetDefaultAudioEndpoint(flow,1,out d); return d; }
    public static float GetVol(int flow, out bool mute) { var d=Dev(flow); Guid iid=typeof(IAudioEndpointVolume).GUID; object o; d.Activate(ref iid,23,IntPtr.Zero,out o);
      var v=(IAudioEndpointVolume)o; float l; v.GetMasterVolumeLevelScalar(out l); v.GetMute(out mute); return l; }
    public static void SetVol(int flow,float l) { var d=Dev(flow); Guid iid=typeof(IAudioEndpointVolume).GUID; object o; d.Activate(ref iid,23,IntPtr.Zero,out o);
      var v=(IAudioEndpointVolume)o; Guid g=Guid.Empty; v.SetMasterVolumeLevelScalar(l,ref g); }
    public static void SetMute(int flow,bool m) { var d=Dev(flow); Guid iid=typeof(IAudioEndpointVolume).GUID; object o; d.Activate(ref iid,23,IntPtr.Zero,out o);
      var v=(IAudioEndpointVolume)o; Guid g=Guid.Empty; v.SetMute(m,ref g); }
    public static float Peak(int flow) { var d=Dev(flow); Guid iid=typeof(IAudioMeterInformation).GUID; object o; d.Activate(ref iid,23,IntPtr.Zero,out o); float p; ((IAudioMeterInformation)o).GetPeakValue(out p); return p; }
    public static string Id(int flow) { string id; Dev(flow).GetId(out id); return id; }
  }
}
'@
$f = if ($Flow -eq 'render') { 0 } else { 1 }
switch ($Cmd) {
  'list'  { foreach ($fl in 0,1) { $m=$false; $v=[CA.Util]::GetVol($fl,[ref]$m); "{0}: id={1} volume={2:N2} mute={3}" -f ($(if($fl){'capture'}else{'render'})), [CA.Util]::Id($fl), $v, $m } }
  'get'   { $m=$false; $v=[CA.Util]::GetVol($f,[ref]$m); "{0} volume={1:N2} mute={2}" -f $Flow,$v,$m }
  'set'   { if ($Level -lt 0 -or $Level -gt 1) { throw 'Level 0..1' }; [CA.Util]::SetVol($f,[single]$Level); $m=$false; "{0} volume now {1:N2}" -f $Flow,[CA.Util]::GetVol($f,[ref]$m) }
  'mute'  { [CA.Util]::SetMute($f, ($Level -ge 1)); $m=$false; $v=[CA.Util]::GetVol($f,[ref]$m); "{0} volume={1:N2} mute={2}" -f $Flow,$v,$m }
  'peak'  { $end=(Get-Date).AddSeconds($Seconds); $mx=0; while((Get-Date) -lt $end){ $p=[CA.Util]::Peak($f); if($p -gt $mx){$mx=$p}; Start-Sleep -Milliseconds 50 }; "{0} peak over {1}s = {2:N4}" -f $Flow,$Seconds,$mx }
}
