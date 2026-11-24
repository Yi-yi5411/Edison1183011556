# 重启 8765 后端：先杀旧进程，再用 WMI 脱离当前作业对象拉起新进程
$ErrorActionPreference = 'Continue'

# 1) 找到占用 8765 的进程并结束
$conns = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $pids) {
  if ($procId -and $procId -ne $PID) {
    Write-Output "Stopping backend pid=$procId"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
  }
}
Start-Sleep -Seconds 1

# 2) WMI 拉起后端（独立进程，不受本终端作业对象回收影响）
$root = 'c:\Users\Administrator\Desktop\structural_inspection'
$python = 'C:\Program Files\python\python.exe'
$cmd = "cmd.exe /c cd /d `"$root\webapp\backend`" && `"$python`" main.py >> `"$root\data\backend_out.log`" 2>&1"
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd }
Write-Output ("WMI create return=" + $result.ReturnValue + " pid=" + $result.ProcessId)

# 3) 等待端口就绪
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $ok = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
  if ($ok) { Write-Output "Backend ready after $i s"; exit 0 }
}
Write-Output "Backend NOT ready after 30 s"
exit 1
