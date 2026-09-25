param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'

# The helper owns a desktop handle and a kill-on-close Job Object. The worker
# starts suspended so descendants cannot escape the job during startup.
try {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class PlaywrightSurveyDesktop {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct STARTUPINFO {
    public int cb; public string lpReserved; public string lpDesktop; public string lpTitle;
    public int dwX,dwY,dwXSize,dwYSize,dwXCountChars,dwYCountChars,dwFillAttribute,dwFlags;
    public short wShowWindow,cbReserved2; public IntPtr lpReserved2,hStdInput,hStdOutput,hStdError;
  }
  [StructLayout(LayoutKind.Sequential)] struct PROCESS_INFORMATION { public IntPtr hProcess,hThread; public uint dwProcessId,dwThreadId; }
  [StructLayout(LayoutKind.Sequential)] struct IO_COUNTERS { public ulong ReadOperationCount,WriteOperationCount,OtherOperationCount,ReadTransferCount,WriteTransferCount,OtherTransferCount; }
  [StructLayout(LayoutKind.Sequential)] struct BASIC_LIMITS { public long PerProcessUserTimeLimit,PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize,MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass,SchedulingClass; }
  [StructLayout(LayoutKind.Sequential)] struct EXTENDED_LIMITS { public BASIC_LIMITS BasicLimitInformation; public IO_COUNTERS IoInfo; public UIntPtr ProcessMemoryLimit,JobMemoryLimit,PeakProcessMemoryUsed,PeakJobMemoryUsed; }
  [DllImport("user32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateDesktopW(string name,IntPtr device,IntPtr mode,uint flags,uint access,IntPtr attributes);
  [DllImport("user32.dll", SetLastError=true)] static extern bool CloseDesktop(IntPtr desktop);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attributes,string name);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int infoClass,ref EXTENDED_LIMITS info,uint length);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string app,StringBuilder command,IntPtr processAttrs,IntPtr threadAttrs,bool inherit,uint flags,IntPtr env,string cwd,ref STARTUPINFO startup,out PROCESS_INFORMATION process);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
  [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint code);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForMultipleObjects(uint count,IntPtr[] handles,bool all,uint milliseconds);
  [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
  [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int which);

  public static string Quote(string value) {
    if (value.Length > 0 && value.IndexOfAny(new char[]{' ', '\t', '\n', '\v', '"'}) < 0) return value;
    var result = new StringBuilder("\""); int slashes = 0;
    foreach (char c in value) {
      if (c == '\\') { slashes++; continue; }
      if (c == '"') { result.Append('\\',slashes * 2 + 1); result.Append('"'); slashes=0; continue; }
      result.Append('\\',slashes); slashes=0; result.Append(c);
    }
    result.Append('\\',slashes * 2); result.Append('"'); return result.ToString();
  }
  static Exception Last(string operation) { return new Win32Exception(Marshal.GetLastWin32Error(),operation); }
  public static int Execute(string application,string[] arguments,string cwd,Dictionary<string,string> env,string name,uint parentPid) {
    IntPtr desktop=IntPtr.Zero,job=IntPtr.Zero,parent=IntPtr.Zero,environment=IntPtr.Zero;
    var child=new PROCESS_INFORMATION(); bool assigned=false;
    try {
      parent=OpenProcess(0x00100000,false,parentPid); if(parent==IntPtr.Zero) throw Last("Open parent process");
      desktop=CreateDesktopW(name,IntPtr.Zero,IntPtr.Zero,0,0x01FF,IntPtr.Zero); if(desktop==IntPtr.Zero) throw Last("Create private desktop");
      job=CreateJobObjectW(IntPtr.Zero,null); if(job==IntPtr.Zero) throw Last("Create process job");
      var limits=new EXTENDED_LIMITS(); limits.BasicLimitInformation.LimitFlags=0x00002000;
      if(!SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(typeof(EXTENDED_LIMITS)))) throw Last("Set job cleanup");
      var startup=new STARTUPINFO(); startup.cb=Marshal.SizeOf(typeof(STARTUPINFO)); startup.lpDesktop=name;
      startup.dwFlags=0x00000100; startup.hStdInput=GetStdHandle(-10); startup.hStdOutput=GetStdHandle(-11); startup.hStdError=GetStdHandle(-12);
      var keys=new List<string>(env.Keys); keys.Sort(StringComparer.OrdinalIgnoreCase);
      var block=new StringBuilder(); foreach(string key in keys) block.Append(key).Append('=').Append(env[key]).Append('\0'); block.Append('\0');
      environment=Marshal.StringToHGlobalUni(block.ToString());
      var command=new StringBuilder(Quote(application)); foreach(string argument in arguments) command.Append(' ').Append(Quote(argument));
      if(!CreateProcessW(application,command,IntPtr.Zero,IntPtr.Zero,true,0x00000004|0x00000400|0x00000200,environment,cwd,ref startup,out child)) throw Last("Create desktop worker");
      if(!AssignProcessToJobObject(job,child.hProcess)) throw Last("Assign desktop worker job"); assigned=true;
      if(ResumeThread(child.hThread)==0xFFFFFFFF) throw Last("Resume desktop worker");
      uint completed=WaitForMultipleObjects(2,new IntPtr[]{child.hProcess,parent},false,0xFFFFFFFF);
      if(completed==1) { TerminateJobObject(job,1); WaitForSingleObject(child.hProcess,5000); return 1; }
      if(completed!=0) throw Last("Wait for desktop worker");
      uint code; if(!GetExitCodeProcess(child.hProcess,out code)) throw Last("Read worker exit code"); return unchecked((int)code);
    } finally {
      if(child.hProcess!=IntPtr.Zero && !assigned) TerminateProcess(child.hProcess,1);
      if(job!=IntPtr.Zero) CloseHandle(job);
      if(child.hThread!=IntPtr.Zero) CloseHandle(child.hThread);
      if(child.hProcess!=IntPtr.Zero) CloseHandle(child.hProcess);
      if(parent!=IntPtr.Zero) CloseHandle(parent);
      if(environment!=IntPtr.Zero) Marshal.FreeHGlobal(environment);
      if(desktop!=IntPtr.Zero) CloseDesktop(desktop);
    }
  }
}
'@
} catch {
  [Console]::Error.WriteLine('error: the Windows desktop helper could not compile.')
  [Console]::Error.WriteLine('hint: check that Add-Type is permitted by the current PowerShell policy.')
  exit 1
}

try {
  $configuration = Get-Content -LiteralPath $ConfigPath -Encoding UTF8 -Raw | ConvertFrom-Json
  $environmentValues = New-Object 'System.Collections.Generic.Dictionary[string,string]'
  foreach ($property in $configuration.env.PSObject.Properties) { $environmentValues[$property.Name] = [string]$property.Value }
  $result = [PlaywrightSurveyDesktop]::Execute([string]$configuration.command, [string[]]$configuration.args, [string]$configuration.cwd, $environmentValues, [string]$configuration.desktop, [uint32]$configuration.parentPid)
  exit $result
} catch {
  [Console]::Error.WriteLine('error: private Windows desktop execution failed: ' + $_.Exception.Message)
  [Console]::Error.WriteLine('hint: check desktop access, PowerShell policy, and browser installation.')
  exit 1
}
