# mic_rec.ps1 - record a named Windows capture device to a 16 kHz mono 16-bit wav (waveIn API, no installs).
# The device is chosen by NAME, never by the Windows default, so a Bluetooth headset microphone can not be picked up by accident.
#   powershell -File tools\mic_rec.ps1 -Seconds 60 -Out file.wav [-Device 'Realtek']
# Prints REC_START / REC_END wall-clock times, the device used, and any buffer-timing gaps.
param([int]$Seconds = 60, [string]$Out = "$env:TEMP\claude\rec.wav", [string]$Device = 'Realtek')
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices; using System.IO; using System.Collections.Generic; using System.Diagnostics;
public static class Rec {
  [StructLayout(LayoutKind.Sequential, Pack=1)] public struct FMT { public ushort tag, ch; public uint rate, avg; public ushort align, bits, cb; }
  [StructLayout(LayoutKind.Sequential)] public struct HDR { public IntPtr data; public uint len, rec; public IntPtr user; public uint flags, loops; public IntPtr next, res; }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Auto)] public struct CAPS { public ushort mid, pid; public uint ver; [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string name; public uint formats; public ushort ch, res; }
  [DllImport("winmm.dll")] static extern uint waveInGetNumDevs();
  [DllImport("winmm.dll", CharSet=CharSet.Auto)] static extern uint waveInGetDevCaps(IntPtr id, ref CAPS c, uint size);
  [DllImport("winmm.dll")] static extern uint waveInOpen(out IntPtr h, uint id, ref FMT f, IntPtr cb, IntPtr inst, uint flags);
  [DllImport("winmm.dll")] static extern uint waveInPrepareHeader(IntPtr h, IntPtr hdr, uint size);
  [DllImport("winmm.dll")] static extern uint waveInUnprepareHeader(IntPtr h, IntPtr hdr, uint size);
  [DllImport("winmm.dll")] static extern uint waveInAddBuffer(IntPtr h, IntPtr hdr, uint size);
  [DllImport("winmm.dll")] static extern uint waveInStart(IntPtr h);
  [DllImport("winmm.dll")] static extern uint waveInStop(IntPtr h);
  [DllImport("winmm.dll")] static extern uint waveInReset(IntPtr h);
  [DllImport("winmm.dll")] static extern uint waveInClose(IntPtr h);
  public static string Run(string match, int seconds, string path, out string startIso, out string endIso, out string note) {
    uint n = waveInGetNumDevs(); int dev = -1; string name = "";
    for (uint i = 0; i < n; i++) { var c = new CAPS(); waveInGetDevCaps((IntPtr)i, ref c, (uint)Marshal.SizeOf(c)); if (c.name.IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0) { dev = (int)i; name = c.name; break; } }
    if (dev < 0) throw new Exception("no capture device matching '" + match + "'");
    var f = new FMT { tag = 1, ch = 1, rate = 16000, avg = 32000, align = 2, bits = 16, cb = 0 };
    IntPtr h; uint r = waveInOpen(out h, (uint)dev, ref f, IntPtr.Zero, IntPtr.Zero, 0); if (r != 0) throw new Exception("waveInOpen " + r);
    int NB = 8, BL = 8000;   // 8 buffers of 0.25 s
    var hdrs = new IntPtr[NB]; int hs = Marshal.SizeOf(typeof(HDR));
    for (int i = 0; i < NB; i++) { var hd = new HDR { data = Marshal.AllocHGlobal(BL), len = (uint)BL }; hdrs[i] = Marshal.AllocHGlobal(hs); Marshal.StructureToPtr(hd, hdrs[i], false); waveInPrepareHeader(h, hdrs[i], (uint)hs); waveInAddBuffer(h, hdrs[i], (uint)hs); }
    var ms = new MemoryStream(); var sw = Stopwatch.StartNew(); startIso = DateTime.Now.ToString("o"); waveInStart(h);
    int next = 0; long target = (long)seconds * 32000; long padded = 0; var gaps = new List<string>(); long lastDone = 0;
    while (ms.Length < target) {
      var hd = (HDR)Marshal.PtrToStructure(hdrs[next], typeof(HDR));
      if ((hd.flags & 1) != 0) {
        long t = sw.ElapsedMilliseconds; if (lastDone > 0 && t - lastDone > 600) gaps.Add(string.Format("gap {0}ms at {1:F2}s", t - lastDone, t / 1000.0)); lastDone = t;
        var b = new byte[hd.rec]; Marshal.Copy(hd.data, b, 0, (int)hd.rec);
        long deficit = t * 16 - (ms.Length + b.Length) / 2;       // samples the wall clock says are missing before this buffer's end
        if (ms.Length > 0 && deficit > 4000) { var z = new byte[deficit * 2]; ms.Write(z, 0, z.Length); padded += deficit; }   // keep the time axis true: zeros for a stall
        ms.Write(b, 0, b.Length);
        hd.flags &= ~1u; Marshal.StructureToPtr(hd, hdrs[next], false); waveInUnprepareHeader(h, hdrs[next], (uint)hs);
        waveInPrepareHeader(h, hdrs[next], (uint)hs); waveInAddBuffer(h, hdrs[next], (uint)hs); next = (next + 1) % NB;
      } else System.Threading.Thread.Sleep(10);
    }
    endIso = DateTime.Now.ToString("o"); waveInStop(h); waveInReset(h); waveInClose(h);
    byte[] pcm = ms.ToArray();
    using (var fs = new FileStream(path, FileMode.Create)) using (var w = new BinaryWriter(fs)) {
      w.Write(new char[] {'R','I','F','F'}); w.Write(36 + pcm.Length); w.Write(new char[] {'W','A','V','E','f','m','t',' '}); w.Write(16); w.Write((short)1); w.Write((short)1);
      w.Write(16000); w.Write(32000); w.Write((short)2); w.Write((short)16); w.Write(new char[] {'d','a','t','a'}); w.Write(pcm.Length); w.Write(pcm); }
    note = (gaps.Count == 0 ? "no buffer gaps" : string.Join("; ", gaps)) + (padded > 0 ? "; padded " + (padded / 16) + " ms of zeros to keep the wall-clock time axis" : "");
    return name;
  }
}
'@
$s = ''; $e = ''; $n = ''
$name = [Rec]::Run($Device, $Seconds, $Out, [ref]$s, [ref]$e, [ref]$n)
Write-Output "DEVICE $name"
Write-Output "REC_START $s"
Write-Output "REC_END $e"
Write-Output "NOTE $n"
